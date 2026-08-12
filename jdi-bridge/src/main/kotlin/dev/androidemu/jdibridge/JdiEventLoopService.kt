package dev.androidemu.jdibridge

import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.VirtualMachine
import com.sun.jdi.event.BreakpointEvent
import com.sun.jdi.event.ClassPrepareEvent
import com.sun.jdi.event.ExceptionEvent
import com.sun.jdi.event.StepEvent
import com.sun.jdi.event.VMDeathEvent
import com.sun.jdi.event.VMDisconnectEvent
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

internal class JdiEventLoopService(
    private val state: JdiSessionState,
    private val breakpointService: JdiBreakpointService,
    private val threadControlService: JdiThreadControlService,
    private val frameValueService: JdiFrameValueService,
    private val emitEvent: (String, JsonObject) -> Unit,
) {
    fun startEventLoop(machine: VirtualMachine) {
        val thread =
            Thread(
                {
                    try {
                        val eventQueue = machine.eventQueue()
                        while (!Thread.currentThread().isInterrupted) {
                            val eventSet =
                                try {
                                    eventQueue.remove(500)
                                } catch (_: InterruptedException) {
                                    break
                                } catch (_: VMDisconnectedException) {
                                    handleDisconnect("VM disconnected")
                                    break
                                }

                            if (eventSet == null) {
                                continue
                            }

                            var shouldStop = false
                            var shouldResumeSet = true
                            try {
                                for (event in eventSet) {
                                    when (event) {
                                        is BreakpointEvent -> {
                                            if (!breakpointService.handleBreakpointEvent(event)) {
                                                shouldResumeSet = false
                                            }
                                        }
                                        is ClassPrepareEvent ->
                                            breakpointService.handleClassPrepareEvent(machine, event)
                                        is ExceptionEvent -> {
                                            if (!breakpointService.handleExceptionEvent(event)) {
                                                shouldResumeSet = false
                                            }
                                        }
                                        is StepEvent -> {
                                            if (!threadControlService.handleStepEvent(machine, event)) {
                                                shouldResumeSet = false
                                            }
                                        }
                                        is com.sun.jdi.event.VMStartEvent -> {
                                            if (state.keepSuspended) {
                                                shouldResumeSet = false
                                            }
                                        }
                                        is VMDisconnectEvent -> {
                                            handleDisconnect("VM disconnected")
                                            shouldStop = true
                                        }
                                        is VMDeathEvent -> {
                                            handleDisconnect("VM death")
                                            shouldStop = true
                                        }
                                    }
                                }
                            } catch (_: VMDisconnectedException) {
                                handleDisconnect("VM disconnected")
                                shouldStop = true
                            } catch (e: Exception) {
                                handleDisconnect("Event loop error: ${e.message}")
                                shouldStop = true
                            } finally {
                                if (shouldResumeSet) {
                                    try {
                                        eventSet.resume()
                                    } catch (_: Exception) {
                                        // Ignore resume failures during shutdown/disconnect.
                                    }
                                }
                            }

                            if (shouldStop) {
                                break
                            }
                        }
                    } catch (_: Exception) {
                        // Outer safety catch.
                    }
                },
                "jdi-event-loop",
            )
        thread.isDaemon = true
        thread.start()
        state.eventThread = thread
    }

    fun stopEventLoop() {
        state.eventThread?.interrupt()
        state.eventThread?.join(2000)
        state.eventThread = null
    }

    fun handleDisconnect(reason: String) {
        // One EventSet can deliver VMDeathEvent alongside another event whose handling
        // then throws VMDisconnectedException, so this runs more than once per disconnect.
        // Report the first cause and drop the rest instead of emitting duplicate
        // notifications and overwriting the reason with a later, less specific one.
        if (!state.disconnectHandled.compareAndSet(false, true)) {
            return
        }

        log("vm disconnected: $reason")
        val normalizedReason = normalizeDisconnectReason(reason)
        state.disconnectReason = normalizedReason
        val pending =
            synchronized(state.lock) {
                val current = state.activeStep
                state.activeStep = null
                state.suspendedAtMs.clear()
                frameValueService.invalidateObjectCacheLocked()
                current
            }
        pending?.completion?.complete(
            buildJsonObject {
                put("status", "timeout")
                put("reason", "${pending.action} interrupted: VM disconnected")
                put(
                    "remediation",
                    "The target process disconnected. Relaunch the app, re-attach the debugger, and retry the step.",
                )
            },
        )

        try {
            emitEvent(
                "vm_disconnected",
                buildJsonObject {
                    put("reason", normalizedReason)
                    put("detail", reason)
                },
            )
        } finally {
            // Flip the observable flag only once the reason has been published. Clients
            // detect disconnection by polling isAttached, so setting it first leaves a
            // window in which a session reads as detached while the explanation for it
            // has not been emitted yet -- and a client that stops polling at that point
            // never learns why. The write is volatile, so observing `disconnected` also
            // guarantees visibility of the emitted event.
            state.disconnected = true
        }
    }

    private fun normalizeDisconnectReason(reason: String): String {
        val lowered = reason.lowercase()
        return when {
            lowered.contains("transport") ||
                lowered.contains("device offline") ||
                lowered.contains("connection reset") -> "device_disconnected"
            lowered.contains("killed") ||
                lowered.contains("terminated") ||
                lowered.contains("force stop") -> "app_killed"
            else -> "app_crashed"
        }
    }
}
