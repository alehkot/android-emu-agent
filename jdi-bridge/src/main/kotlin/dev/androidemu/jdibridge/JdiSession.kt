package dev.androidemu.jdibridge

import com.sun.jdi.Bootstrap
import com.sun.jdi.VirtualMachine
import com.sun.jdi.connect.AttachingConnector
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Manages a single JDI connection to a target JVM.
 *
 * Thread safety: [status] and command handlers may run on the main RPC thread while the event loop
 * consumes JDI events on a background daemon thread.
 */
class JdiSession(
    private val notificationEmitter: (JsonElement) -> Unit,
) {
    companion object {
        const val DEFAULT_STEP_TIMEOUT_SECONDS = 10.0
        const val DEFAULT_LOGPOINT_STACK_FRAMES = 8
        const val ANR_WARNING_SECONDS = 8.0
    }

    private val state = JdiSessionState()
    private val inspector = Inspector()
    private val frameValueService = JdiFrameValueService(state, inspector)
    private val threadControlService = JdiThreadControlService(state, frameValueService)
    private val breakpointService =
        JdiBreakpointService(
            state = state,
            threadControlService = threadControlService,
            frameValueService = frameValueService,
            emitEvent = this::emitEvent,
        )
    private val eventLoopService =
        JdiEventLoopService(
            state = state,
            breakpointService = breakpointService,
            threadControlService = threadControlService,
            frameValueService = frameValueService,
            emitEvent = this::emitEvent,
        )

    val isAttached: Boolean
        get() = state.vm != null && !state.disconnected

    fun attach(host: String, port: Int, keepSuspended: Boolean = false): JsonElement {
        if (state.vm != null) {
            throw RpcException(INVALID_REQUEST, "Already attached to a VM; detach first")
        }

        val connector = findSocketAttachConnector()
        val args = connector.defaultArguments()
        args["hostname"]!!.setValue(host)
        args["port"]!!.setValue(port.toString())
        args["timeout"]!!.setValue("5000")

        log("attaching to $host:$port")
        val machine =
            try {
                connector.attach(args)
            } catch (e: Exception) {
                val detail = e.message ?: "unknown"
                val lowered = detail.lowercase()
                if (lowered.contains("handshake") || lowered.contains("not debuggable")) {
                    throw RpcException(INTERNAL_ERROR, "APP_NOT_DEBUGGABLE: $detail")
                }
                throw RpcException(INTERNAL_ERROR, "Failed to attach: $detail")
            }

        state.vm = machine
        state.disconnected = false
        state.disconnectReason = null
        synchronized(state.lock) {
            state.breakpoints.clear()
            state.nextBreakpointId = 1
            state.activeStep = null
            state.suspendedAtMs.clear()
            frameValueService.invalidateObjectCacheLocked()
        }

        if (!keepSuspended && machine.allThreads().all { it.isSuspended }) {
            log("vm fully suspended, resuming")
            machine.resume()
        }

        eventLoopService.startEventLoop(machine)

        return buildJsonObject {
            put("status", "attached")
            put("vm_name", machine.name())
            put("vm_version", machine.version())
            put("thread_count", machine.allThreads().size)
            put("suspended", machine.allThreads().all { it.isSuspended })
            put("keep_suspended", keepSuspended)
        }
    }

    fun detach(): JsonElement {
        val machine = state.vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")

        eventLoopService.stopEventLoop()
        breakpointService.clearBreakpointRequests(machine)
        breakpointService.clearExceptionBreakpointRequests(machine)
        try {
            machine.dispose()
        } catch (_: Exception) {
            // VM may already be gone
        }
        state.vm = null
        state.disconnected = false
        state.disconnectReason = null
        synchronized(state.lock) {
            state.activeStep = null
            state.suspendedAtMs.clear()
            frameValueService.invalidateObjectCacheLocked()
        }
        state.mapping = null

        return buildJsonObject { put("status", "detached") }
    }

    fun loadMapping(path: String): JsonElement {
        val loaded = ProguardMapping.load(path)
        state.mapping = loaded
        return buildJsonObject {
            put("status", "loaded")
            put("path", path)
            put("class_count", loaded.classCount)
            put("member_count", loaded.memberCount)
        }
    }

    fun clearMapping(): JsonElement {
        state.mapping = null
        return buildJsonObject { put("status", "cleared") }
    }

    fun status(): JsonElement {
        val machine = state.vm
        if (machine == null) {
            return buildJsonObject { put("status", "not_attached") }
        }

        if (state.disconnected) {
            return buildJsonObject {
                put("status", "disconnected")
                put("reason", state.disconnectReason ?: "unknown")
            }
        }

        return try {
            buildJsonObject {
                put("status", "attached")
                put("vm_name", machine.name())
                put("vm_version", machine.version())
                put("thread_count", machine.allThreads().size)
                put("suspended", machine.allThreads().all { it.isSuspended })
            }
        } catch (e: Exception) {
            buildJsonObject {
                put("status", "disconnected")
                put("reason", e.message ?: "unknown")
            }
        }
    }

    fun setBreakpoint(
        classPattern: String,
        line: Int,
        condition: String? = null,
        logMessage: String? = null,
        captureStack: Boolean = false,
        stackMaxFrames: Int = DEFAULT_LOGPOINT_STACK_FRAMES,
    ): JsonElement {
        val machine = requireAttachedMachine()
        return breakpointService.setBreakpoint(
            machine = machine,
            classPattern = classPattern,
            line = line,
            condition = condition,
            logMessage = logMessage,
            captureStack = captureStack,
            stackMaxFrames = stackMaxFrames,
        )
    }

    fun removeBreakpoint(breakpointId: Int): JsonElement {
        val machine = requireAttachedMachine()
        return breakpointService.removeBreakpoint(machine, breakpointId)
    }

    fun listBreakpoints(): JsonElement {
        requireAttachedMachine()
        return breakpointService.listBreakpoints()
    }

    fun setExceptionBreakpoint(
        classPattern: String,
        caught: Boolean,
        uncaught: Boolean,
    ): JsonElement {
        val machine = requireAttachedMachine()
        return breakpointService.setExceptionBreakpoint(
            machine = machine,
            classPattern = classPattern,
            caught = caught,
            uncaught = uncaught,
        )
    }

    fun removeExceptionBreakpoint(breakpointId: Int): JsonElement {
        val machine = requireAttachedMachine()
        return breakpointService.removeExceptionBreakpoint(machine, breakpointId)
    }

    fun listExceptionBreakpoints(): JsonElement {
        requireAttachedMachine()
        return breakpointService.listExceptionBreakpoints()
    }

    fun listThreads(includeDaemon: Boolean, maxThreads: Int): JsonElement {
        val machine = requireAttachedMachine()
        return threadControlService.listThreads(machine, includeDaemon, maxThreads)
    }

    fun stepOver(
        threadName: String,
        timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        val machine = requireAttachedMachine()
        return threadControlService.stepOver(machine, threadName, timeoutSeconds)
    }

    fun stepInto(
        threadName: String,
        timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        val machine = requireAttachedMachine()
        return threadControlService.stepInto(machine, threadName, timeoutSeconds)
    }

    fun stepOut(
        threadName: String,
        timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        val machine = requireAttachedMachine()
        return threadControlService.stepOut(machine, threadName, timeoutSeconds)
    }

    fun resume(threadName: String?): JsonElement {
        val machine = requireAttachedMachine()
        return threadControlService.resume(machine, threadName)
    }

    fun stackTrace(threadName: String, maxFrames: Int): JsonElement {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        val machine = requireAttachedMachine()
        val thread = threadControlService.resolveThread(machine, threadName)
        return frameValueService.stackTrace(thread, maxFrames)
    }

    fun inspectVariable(
        threadName: String,
        frameIndex: Int,
        variablePath: String,
        depth: Int,
    ): JsonElement {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        val machine = requireAttachedMachine()
        val thread = threadControlService.resolveThread(machine, threadName)
        return frameValueService.inspectVariable(thread, frameIndex, variablePath, depth)
    }

    fun evaluate(
        threadName: String,
        frameIndex: Int,
        expression: String,
    ): JsonElement {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        val machine = requireAttachedMachine()
        val thread = threadControlService.resolveThread(machine, threadName)
        return frameValueService.evaluate(thread, frameIndex, expression)
    }

    private fun requireAttachedMachine(): VirtualMachine {
        if (state.disconnected) {
            throw RpcException(INVALID_REQUEST, "VM is disconnected: ${state.disconnectReason ?: "unknown"}")
        }
        return state.vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")
    }

    private fun emitEvent(type: String, extraParams: JsonObject) {
        val payload = buildJsonObject {
            put("jsonrpc", "2.0")
            put("method", "event")
            put(
                "params",
                buildJsonObject {
                    put("type", type)
                    for ((key, value) in extraParams) {
                        put(key, value)
                    }
                },
            )
        }

        try {
            notificationEmitter(payload)
        } catch (_: Exception) {
            // Best effort
        }
    }

    private fun findSocketAttachConnector(): AttachingConnector {
        val vmm = Bootstrap.virtualMachineManager()
        return vmm.attachingConnectors().firstOrNull { it.name() == "com.sun.jdi.SocketAttach" }
            ?: throw RpcException(INTERNAL_ERROR, "SocketAttach connector not found in JDK")
    }
}
