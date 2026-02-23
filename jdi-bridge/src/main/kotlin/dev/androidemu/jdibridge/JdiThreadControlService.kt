package dev.androidemu.jdibridge

import com.sun.jdi.BooleanValue
import com.sun.jdi.ThreadReference
import com.sun.jdi.VirtualMachine
import com.sun.jdi.event.StepEvent
import com.sun.jdi.request.EventRequest
import com.sun.jdi.request.StepRequest
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

internal class JdiThreadControlService(
    private val state: JdiSessionState,
    private val frameValueService: JdiFrameValueService,
) {
    fun listThreads(machine: VirtualMachine, includeDaemon: Boolean, maxThreads: Int): JsonElement {
        if (maxThreads <= 0) {
            throw RpcException(INVALID_PARAMS, "max_threads must be > 0")
        }

        val allThreads =
            try {
                machine.allThreads()
            } catch (e: Exception) {
                throw RpcException(INTERNAL_ERROR, "Failed to list threads: ${e.message}")
            }

        val filtered =
            if (includeDaemon) {
                allThreads
            } else {
                allThreads.filter { !isDaemonThread(it) }
            }

        val total = filtered.size
        val limited = filtered.take(maxThreads)

        return buildJsonObject {
            put(
                "threads",
                JsonArray(
                    limited.map { thread ->
                        buildJsonObject {
                            put("name", thread.name())
                            put("state", mapThreadState(thread))
                            put("daemon", isDaemonThread(thread))
                        }
                    },
                ),
            )
            put("total_threads", total)
            put("shown_threads", limited.size)
            put("truncated", total > limited.size)
            put("include_daemon", includeDaemon)
            put("max_threads", maxThreads)
        }
    }

    fun stepOver(
        machine: VirtualMachine,
        threadName: String,
        timeoutSeconds: Double,
    ): JsonObject {
        return performStep(
            machine = machine,
            action = "step_over",
            threadName = threadName,
            timeoutSeconds = timeoutSeconds,
            depth = StepRequest.STEP_OVER,
        )
    }

    fun stepInto(
        machine: VirtualMachine,
        threadName: String,
        timeoutSeconds: Double,
    ): JsonObject {
        return performStep(
            machine = machine,
            action = "step_into",
            threadName = threadName,
            timeoutSeconds = timeoutSeconds,
            depth = StepRequest.STEP_INTO,
        )
    }

    fun stepOut(
        machine: VirtualMachine,
        threadName: String,
        timeoutSeconds: Double,
    ): JsonObject {
        return performStep(
            machine = machine,
            action = "step_out",
            threadName = threadName,
            timeoutSeconds = timeoutSeconds,
            depth = StepRequest.STEP_OUT,
        )
    }

    fun resume(machine: VirtualMachine, threadName: String?): JsonElement {
        if (threadName == null) {
            try {
                machine.resume()
            } catch (e: Exception) {
                throw RpcException(INTERNAL_ERROR, "Failed to resume VM: ${e.message ?: "unknown"}")
            }
            synchronized(state.lock) {
                state.suspendedAtMs.clear()
                frameValueService.invalidateObjectCacheLocked()
            }
            return buildJsonObject {
                put("status", "resumed")
                put("scope", "all")
            }
        }

        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }

        val thread = resolveThread(machine, threadName)
        try {
            var attempts = 0
            while (thread.isSuspended && attempts < 32) {
                thread.resume()
                attempts += 1
            }
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to resume thread: ${e.message ?: "unknown"}")
        }
        markThreadResumed(thread)
        synchronized(state.lock) { frameValueService.invalidateObjectCacheLocked() }

        return buildJsonObject {
            put("status", "resumed")
            put("scope", "thread")
            put("thread", thread.name())
        }
    }

    fun resolveThread(machine: VirtualMachine, threadName: String): ThreadReference {
        val threads =
            try {
                machine.allThreads()
            } catch (e: Exception) {
                throw RpcException(INTERNAL_ERROR, "Failed to list threads: ${e.message ?: "unknown"}")
            }
        return threads.firstOrNull { it.name() == threadName }
            ?: throw RpcException(INVALID_REQUEST, "Thread not found: $threadName")
    }

    fun handleStepEvent(machine: VirtualMachine, event: StepEvent): Boolean {
        val stepRequest = event.request() as? StepRequest ?: return true

        val pending =
            synchronized(state.lock) {
                val current = state.activeStep
                if (current == null || current.request != stepRequest) {
                    null
                } else {
                    state.activeStep = null
                    current
                }
            }

        if (pending == null) {
            clearStepRequest(machine, stepRequest)
            return true
        }

        clearStepRequest(machine, stepRequest)
        val payload = frameValueService.buildStoppedPayload(event.thread(), event.location())
        markThreadSuspended(event.thread())
        pending.completion.complete(payload)

        // Keep thread suspended on the new line for follow-up step/inspect commands.
        return false
    }

    fun markThreadSuspended(thread: ThreadReference) {
        synchronized(state.lock) {
            state.suspendedAtMs.getOrPut(thread.uniqueID()) { System.currentTimeMillis() }
        }
    }

    fun markThreadResumed(thread: ThreadReference) {
        synchronized(state.lock) { state.suspendedAtMs.remove(thread.uniqueID()) }
    }

    private fun performStep(
        machine: VirtualMachine,
        action: String,
        threadName: String,
        timeoutSeconds: Double,
        depth: Int,
    ): JsonObject {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        if (timeoutSeconds <= 0.0) {
            throw RpcException(INVALID_PARAMS, "timeout_seconds must be > 0")
        }

        val thread = resolveThread(machine, threadName)

        synchronized(state.lock) {
            if (state.activeStep != null) {
                throw RpcException(INVALID_REQUEST, "Another step command is already in progress")
            }
        }

        if (!thread.isSuspended) {
            try {
                thread.suspend()
            } catch (e: Exception) {
                throw RpcException(INTERNAL_ERROR, "Failed to suspend thread: ${e.message ?: "unknown"}")
            }
        }
        markThreadSuspended(thread)

        clearExistingStepRequests(machine, thread)

        val request =
            machine
                .eventRequestManager()
                .createStepRequest(
                    thread,
                    StepRequest.STEP_LINE,
                    depth,
                ).apply {
                    addCountFilter(1)
                    setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                    putProperty("step_action", action)
                    enable()
                }

        val completion = CompletableFuture<JsonObject>()
        synchronized(state.lock) {
            state.activeStep =
                PendingStep(
                    action = action,
                    threadName = thread.name(),
                    request = request,
                    completion = completion,
                )
            frameValueService.invalidateObjectCacheLocked()
        }

        try {
            thread.resume()
        } catch (e: Exception) {
            clearStepRequest(machine, request)
            synchronized(state.lock) {
                if (state.activeStep?.request == request) {
                    state.activeStep = null
                }
            }
            throw RpcException(
                INTERNAL_ERROR,
                "Failed to resume thread for step: ${e.message ?: "unknown"}",
            )
        }

        return try {
            completion.get((timeoutSeconds * 1000).toLong(), TimeUnit.MILLISECONDS)
        } catch (_: TimeoutException) {
            clearStepRequest(machine, request)
            synchronized(state.lock) {
                if (state.activeStep?.request == request) {
                    state.activeStep = null
                }
            }
            buildJsonObject {
                put("status", "timeout")
                put("reason", "$action did not complete within ${timeoutSeconds.toInt()}s")
                put(
                    "remediation",
                    "The app may be blocked on I/O or in a loop. Use 'debug resume' to continue, then set a breakpoint further ahead.",
                )
            }
        } catch (e: Exception) {
            clearStepRequest(machine, request)
            synchronized(state.lock) {
                if (state.activeStep?.request == request) {
                    state.activeStep = null
                }
            }
            throw RpcException(INTERNAL_ERROR, "Step failed: ${e.message ?: "unknown"}")
        }
    }

    private fun clearStepRequest(machine: VirtualMachine, stepRequest: StepRequest) {
        try {
            machine.eventRequestManager().deleteEventRequest(stepRequest)
        } catch (_: Exception) {
            // Best effort cleanup.
        }
    }

    private fun clearExistingStepRequests(machine: VirtualMachine, thread: ThreadReference) {
        val manager = machine.eventRequestManager()
        val existing =
            try {
                manager.stepRequests().filter { it.thread() == thread }
            } catch (_: Exception) {
                emptyList()
            }
        for (request in existing) {
            clearStepRequest(machine, request)
        }
    }

    private fun mapThreadState(thread: ThreadReference): String {
        if (thread.isSuspended) {
            return "SUSPENDED"
        }

        return when (thread.status()) {
            ThreadReference.THREAD_STATUS_RUNNING -> "RUNNING"
            ThreadReference.THREAD_STATUS_SLEEPING,
            ThreadReference.THREAD_STATUS_WAIT,
            ThreadReference.THREAD_STATUS_MONITOR,
            ThreadReference.THREAD_STATUS_NOT_STARTED,
            ThreadReference.THREAD_STATUS_UNKNOWN,
            ThreadReference.THREAD_STATUS_ZOMBIE, -> "WAITING"
            else -> "WAITING"
        }
    }

    private fun isDaemonThread(thread: ThreadReference): Boolean {
        return try {
            val daemonField = thread.referenceType().allFields().firstOrNull { it.name() == "daemon" } ?: return false
            val value = thread.getValue(daemonField)
            (value as? BooleanValue)?.value() ?: false
        } catch (_: Exception) {
            false
        }
    }
}
