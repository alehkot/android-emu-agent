package dev.androidemu.jdibridge

import com.sun.jdi.AbsentInformationException
import com.sun.jdi.BooleanValue
import com.sun.jdi.Bootstrap
import com.sun.jdi.ByteValue
import com.sun.jdi.CharValue
import com.sun.jdi.ClassType
import com.sun.jdi.DoubleValue
import com.sun.jdi.FloatValue
import com.sun.jdi.IncompatibleThreadStateException
import com.sun.jdi.IntegerValue
import com.sun.jdi.Location
import com.sun.jdi.LongValue
import com.sun.jdi.ObjectCollectedException
import com.sun.jdi.ObjectReference
import com.sun.jdi.PrimitiveValue
import com.sun.jdi.ShortValue
import com.sun.jdi.StackFrame
import com.sun.jdi.StringReference
import com.sun.jdi.ThreadReference
import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.Value
import com.sun.jdi.VirtualMachine
import com.sun.jdi.connect.AttachingConnector
import com.sun.jdi.event.BreakpointEvent
import com.sun.jdi.event.ClassPrepareEvent
import com.sun.jdi.event.ExceptionEvent
import com.sun.jdi.event.StepEvent
import com.sun.jdi.event.VMDeathEvent
import com.sun.jdi.event.VMDisconnectEvent
import com.sun.jdi.request.BreakpointRequest
import com.sun.jdi.request.ClassPrepareRequest
import com.sun.jdi.request.EventRequest
import com.sun.jdi.request.ExceptionRequest
import com.sun.jdi.request.StepRequest
import java.util.Locale
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
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
        const val ANR_WARNING_SECONDS = 8.0
        private const val ERR_NOT_SUSPENDED = "ERR_NOT_SUSPENDED"
        private const val ERR_OBJECT_COLLECTED = "ERR_OBJECT_COLLECTED"
        private const val ERR_EVAL_UNSUPPORTED = "ERR_EVAL_UNSUPPORTED"
    }

    private data class BreakpointState(
            val id: Int,
            val classPattern: String,
            val line: Int,
            var status: String,
            var location: String? = null,
            var request: BreakpointRequest? = null,
            var prepareRequest: ClassPrepareRequest? = null,
            val condition: String? = null,
            val logMessage: String? = null,
            var hitCount: Long = 0,
    )

    private data class ExceptionBreakpointState(
            val id: Int,
            val classPattern: String,
            val caught: Boolean,
            val uncaught: Boolean,
            var status: String,
            var request: ExceptionRequest? = null,
            var prepareRequest: ClassPrepareRequest? = null,
    )

    private data class PendingStep(
            val action: String,
            val threadName: String,
            val request: StepRequest,
            val completion: CompletableFuture<JsonObject>,
    )

    @Volatile private var vm: VirtualMachine? = null

    @Volatile private var eventThread: Thread? = null

    @Volatile private var disconnected = false

    @Volatile private var disconnectReason: String? = null

    private val stateLock = Any()
    private val breakpoints = linkedMapOf<Int, BreakpointState>()
    private val exceptionBreakpoints = linkedMapOf<Int, ExceptionBreakpointState>()
    private var nextBreakpointId = 1
    private var activeStep: PendingStep? = null
    private val inspector = Inspector()
    private val suspendedAtMs = mutableMapOf<Long, Long>()
    private val objectIdsByUniqueId = mutableMapOf<Long, String>()
    private val objectRefsById = mutableMapOf<String, ObjectReference>()
    private var nextObjectId = 1
    @Volatile private var mapping: ProguardMapping? = null

    val isAttached: Boolean
        get() = vm != null && !disconnected

    fun attach(host: String, port: Int): JsonElement {
        if (vm != null) {
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

        vm = machine
        disconnected = false
        disconnectReason = null
        synchronized(stateLock) {
            breakpoints.clear()
            nextBreakpointId = 1
            activeStep = null
            suspendedAtMs.clear()
            invalidateObjectCacheLocked()
        }

        // If the VM is fully suspended (wait-for-debugger), resume it
        if (machine.allThreads().all { it.isSuspended }) {
            log("vm fully suspended, resuming")
            machine.resume()
        }

        startEventLoop(machine)

        return buildJsonObject {
            put("status", "attached")
            put("vm_name", machine.name())
            put("vm_version", machine.version())
            put("thread_count", machine.allThreads().size)
            put("suspended", machine.allThreads().all { it.isSuspended })
        }
    }

    fun detach(): JsonElement {
        val machine = vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")

        stopEventLoop()
        clearBreakpointRequests(machine)
        clearExceptionBreakpointRequests(machine)
        try {
            machine.dispose()
        } catch (_: Exception) {
            // VM may already be gone
        }
        vm = null
        disconnected = false
        disconnectReason = null
        synchronized(stateLock) {
            activeStep = null
            suspendedAtMs.clear()
            invalidateObjectCacheLocked()
        }
        mapping = null

        return buildJsonObject { put("status", "detached") }
    }

    fun loadMapping(path: String): JsonElement {
        val loaded = ProguardMapping.load(path)
        mapping = loaded
        return buildJsonObject {
            put("status", "loaded")
            put("path", path)
            put("class_count", loaded.classCount)
            put("member_count", loaded.memberCount)
        }
    }

    fun clearMapping(): JsonElement {
        mapping = null
        return buildJsonObject { put("status", "cleared") }
    }

    fun status(): JsonElement {
        val machine = vm
        if (machine == null) {
            return buildJsonObject { put("status", "not_attached") }
        }

        if (disconnected) {
            return buildJsonObject {
                put("status", "disconnected")
                put("reason", disconnectReason ?: "unknown")
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
    ): JsonElement {
        if (line <= 0) {
            throw RpcException(INVALID_PARAMS, "line must be > 0")
        }

        val machine = requireAttachedMachine()
        val breakpointId =
                synchronized(stateLock) {
                    val id = nextBreakpointId
                    nextBreakpointId += 1
                    id
                }

        val resolvedLocation = findLoadedLocation(machine, classPattern, line)
        if (resolvedLocation != null) {
            val request = createEnabledBreakpoint(machine, resolvedLocation, breakpointId)
            val locationText = formatLocation(resolvedLocation)
            synchronized(stateLock) {
                breakpoints[breakpointId] =
                        BreakpointState(
                                id = breakpointId,
                                classPattern = classPattern,
                                line = line,
                                status = "set",
                                location = locationText,
                                request = request,
                                condition = condition,
                                logMessage = logMessage,
                        )
            }
            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("location", locationText)
                if (condition != null) {
                    put("condition", condition)
                }
                if (logMessage != null) {
                    put("log_message", logMessage)
                }
            }
        }

        val prepareRequest =
                machine.eventRequestManager().createClassPrepareRequest().apply {
                    addClassFilter(classPattern)
                    setSuspendPolicy(EventRequest.SUSPEND_NONE)
                    putProperty("breakpoint_id", breakpointId)
                    enable()
                }

        synchronized(stateLock) {
            breakpoints[breakpointId] =
                    BreakpointState(
                            id = breakpointId,
                            classPattern = classPattern,
                            line = line,
                            status = "pending",
                            prepareRequest = prepareRequest,
                            condition = condition,
                            logMessage = logMessage,
                    )
        }

        return buildJsonObject {
            put("status", "pending")
            put("breakpoint_id", breakpointId)
            put("reason", "class_not_loaded")
            put("class_pattern", classPattern)
            put("line", line)
            if (condition != null) {
                put("condition", condition)
            }
            if (logMessage != null) {
                put("log_message", logMessage)
            }
        }
    }

    fun removeBreakpoint(breakpointId: Int): JsonElement {
        if (breakpointId <= 0) {
            throw RpcException(INVALID_PARAMS, "breakpoint_id must be > 0")
        }

        val machine = requireAttachedMachine()
        val state =
                synchronized(stateLock) { breakpoints.remove(breakpointId) }
                        ?: throw RpcException(
                                INVALID_REQUEST,
                                "Unknown breakpoint_id: $breakpointId"
                        )

        val manager = machine.eventRequestManager()
        state.request?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup for stale requests
            }
        }
        state.prepareRequest?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup for stale requests
            }
        }

        return buildJsonObject {
            put("status", "removed")
            put("breakpoint_id", breakpointId)
        }
    }

    fun listBreakpoints(): JsonElement {
        requireAttachedMachine()
        val snapshot =
                synchronized(stateLock) {
                    breakpoints.values.map {
                        BreakpointState(
                                id = it.id,
                                classPattern = it.classPattern,
                                line = it.line,
                                status = it.status,
                                location = it.location,
                                condition = it.condition,
                                logMessage = it.logMessage,
                                hitCount = it.hitCount,
                        )
                    }
                }

        return buildJsonObject {
            put("count", snapshot.size)
            put(
                    "breakpoints",
                    JsonArray(
                            snapshot.map { bp ->
                                buildJsonObject {
                                    put("breakpoint_id", bp.id)
                                    put("class_pattern", bp.classPattern)
                                    put("line", bp.line)
                                    put("status", bp.status)
                                    if (bp.location != null) {
                                        put("location", bp.location)
                                    }
                                    if (bp.condition != null) {
                                        put("condition", bp.condition)
                                    }
                                    if (bp.logMessage != null) {
                                        put("log_message", bp.logMessage)
                                        put("hit_count", bp.hitCount)
                                    }
                                }
                            }
                    )
            )
        }
    }

    fun setExceptionBreakpoint(
            classPattern: String,
            caught: Boolean,
            uncaught: Boolean,
    ): JsonElement {
        if (!caught && !uncaught) {
            throw RpcException(INVALID_PARAMS, "At least one of caught or uncaught must be true")
        }

        val machine = requireAttachedMachine()
        val breakpointId =
                synchronized(stateLock) {
                    val id = nextBreakpointId
                    nextBreakpointId += 1
                    id
                }

        // Try to find the exception class if it's already loaded.
        val refType =
                if (classPattern == "*" || classPattern.isEmpty()) {
                    null // null means "all exceptions"
                } else {
                    machine.classesByName(classPattern).firstOrNull()
                }

        val isWildcard = classPattern == "*" || classPattern.isEmpty()

        if (refType != null || isWildcard) {
            val exReq =
                    machine.eventRequestManager()
                            .createExceptionRequest(
                                    refType,
                                    caught,
                                    uncaught,
                            )
                            .apply {
                                setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                                putProperty("breakpoint_id", breakpointId)
                                enable()
                            }

            synchronized(stateLock) {
                exceptionBreakpoints[breakpointId] =
                        ExceptionBreakpointState(
                                id = breakpointId,
                                classPattern = if (isWildcard) "*" else classPattern,
                                caught = caught,
                                uncaught = uncaught,
                                status = "set",
                                request = exReq,
                        )
            }

            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("class_pattern", if (isWildcard) "*" else classPattern)
                put("caught", caught)
                put("uncaught", uncaught)
            }
        }

        // Class not yet loaded — register deferred.
        val prepareReq =
                machine.eventRequestManager().createClassPrepareRequest().apply {
                    addClassFilter(classPattern)
                    setSuspendPolicy(EventRequest.SUSPEND_NONE)
                    putProperty("exception_breakpoint_id", breakpointId)
                    enable()
                }

        synchronized(stateLock) {
            exceptionBreakpoints[breakpointId] =
                    ExceptionBreakpointState(
                            id = breakpointId,
                            classPattern = classPattern,
                            caught = caught,
                            uncaught = uncaught,
                            status = "pending",
                            prepareRequest = prepareReq,
                    )
        }

        return buildJsonObject {
            put("status", "pending")
            put("breakpoint_id", breakpointId)
            put("reason", "class_not_loaded")
            put("class_pattern", classPattern)
            put("caught", caught)
            put("uncaught", uncaught)
        }
    }

    fun removeExceptionBreakpoint(breakpointId: Int): JsonElement {
        if (breakpointId <= 0) {
            throw RpcException(INVALID_PARAMS, "breakpoint_id must be > 0")
        }

        val machine = requireAttachedMachine()
        val state =
                synchronized(stateLock) { exceptionBreakpoints.remove(breakpointId) }
                        ?: throw RpcException(
                                INVALID_REQUEST,
                                "Unknown exception breakpoint_id: $breakpointId"
                        )

        val manager = machine.eventRequestManager()
        state.request?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup
            }
        }
        state.prepareRequest?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup
            }
        }

        return buildJsonObject {
            put("status", "removed")
            put("breakpoint_id", breakpointId)
        }
    }

    fun listExceptionBreakpoints(): JsonElement {
        requireAttachedMachine()
        val snapshot =
                synchronized(stateLock) {
                    exceptionBreakpoints.values.map {
                        ExceptionBreakpointState(
                                id = it.id,
                                classPattern = it.classPattern,
                                caught = it.caught,
                                uncaught = it.uncaught,
                                status = it.status,
                        )
                    }
                }

        return buildJsonObject {
            put("count", snapshot.size)
            put(
                    "exception_breakpoints",
                    JsonArray(
                            snapshot.map { bp ->
                                buildJsonObject {
                                    put("breakpoint_id", bp.id)
                                    put("class_pattern", bp.classPattern)
                                    put("caught", bp.caught)
                                    put("uncaught", bp.uncaught)
                                    put("status", bp.status)
                                }
                            }
                    )
            )
        }
    }

    fun listThreads(includeDaemon: Boolean, maxThreads: Int): JsonElement {
        if (maxThreads <= 0) {
            throw RpcException(INVALID_PARAMS, "max_threads must be > 0")
        }

        val machine = requireAttachedMachine()
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
                            }
                    )
            )
            put("total_threads", total)
            put("shown_threads", limited.size)
            put("truncated", total > limited.size)
            put("include_daemon", includeDaemon)
            put("max_threads", maxThreads)
        }
    }

    fun stepOver(
            threadName: String,
            timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        return performStep(
                action = "step_over",
                threadName = threadName,
                timeoutSeconds = timeoutSeconds,
                depth = StepRequest.STEP_OVER,
        )
    }

    fun stepInto(
            threadName: String,
            timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        return performStep(
                action = "step_into",
                threadName = threadName,
                timeoutSeconds = timeoutSeconds,
                depth = StepRequest.STEP_INTO,
        )
    }

    fun stepOut(
            threadName: String,
            timeoutSeconds: Double = DEFAULT_STEP_TIMEOUT_SECONDS,
    ): JsonElement {
        return performStep(
                action = "step_out",
                threadName = threadName,
                timeoutSeconds = timeoutSeconds,
                depth = StepRequest.STEP_OUT,
        )
    }

    fun resume(threadName: String?): JsonElement {
        val machine = requireAttachedMachine()
        if (threadName == null) {
            try {
                machine.resume()
            } catch (e: Exception) {
                throw RpcException(INTERNAL_ERROR, "Failed to resume VM: ${e.message ?: "unknown"}")
            }
            synchronized(stateLock) {
                suspendedAtMs.clear()
                invalidateObjectCacheLocked()
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
        synchronized(stateLock) { invalidateObjectCacheLocked() }

        return buildJsonObject {
            put("status", "resumed")
            put("scope", "thread")
            put("thread", thread.name())
        }
    }

    fun stackTrace(threadName: String, maxFrames: Int): JsonElement {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        if (maxFrames <= 0) {
            throw RpcException(INVALID_PARAMS, "max_frames must be > 0")
        }

        val machine = requireAttachedMachine()
        val thread = resolveThread(machine, threadName)
        val frames = requireThreadFrames(thread)
        val activeMapping = mapping

        val entries = mutableListOf<JsonObject>()
        var index = 0
        while (index < frames.size && entries.size < maxFrames) {
            val frame = frames[index]
            val location = frame.location()
            if (FrameFilter.isCoroutineInternal(location)) {
                var filteredCount = 0
                while (index < frames.size &&
                        FrameFilter.isCoroutineInternal(frames[index].location())) {
                    filteredCount += 1
                    index += 1
                }
                entries.add(
                        buildJsonObject {
                            put("filtered", true)
                            put("count", filteredCount)
                            put("reason", "coroutine_internal")
                        },
                )
                continue
            }

            entries.add(
                    buildJsonObject {
                        val rawClassName = location.declaringType().name()
                        val method = location.method()
                        val methodArity =
                                runCatching { method.argumentTypeNames().size }.getOrNull()
                        put("index", index)
                        put("class", activeMapping?.deobfuscateClass(rawClassName) ?: rawClassName)
                        put(
                                "method",
                                activeMapping?.deobfuscateMethod(
                                        rawClassName,
                                        method.name(),
                                        methodArity
                                )
                                        ?: method.name(),
                        )
                        put("line", location.lineNumber())
                        val source = runCatching { location.sourceName() }.getOrNull()
                        if (source != null) {
                            put("source", source)
                        }
                    },
            )
            index += 1
        }

        val truncated = index < frames.size
        return buildJsonObject {
            put("thread", thread.name())
            put("frame_count", frames.size)
            put("frames", JsonArray(entries))
            put("truncated", truncated)
            put("total_frames", frames.size)
            put("shown_frames", entries.size)
            put("max_frames", maxFrames)
        }
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
        if (frameIndex < 0) {
            throw RpcException(INVALID_PARAMS, "frame_index must be >= 0")
        }
        if (depth <= 0 || depth > 3) {
            throw RpcException(INVALID_PARAMS, "depth must be in range 1..3")
        }
        if (variablePath.isBlank()) {
            throw RpcException(INVALID_PARAMS, "variable_path must not be blank")
        }

        val machine = requireAttachedMachine()
        val thread = resolveThread(machine, threadName)
        val frame = resolveFrame(thread, frameIndex)
        val value = resolveValuePath(frame, variablePath)
        val activeMapping = mapping
        val inspected =
                inspector.inspectValue(
                        value = value,
                        depth = depth,
                        tokenBudget = TokenBudget.DEFAULT_MAX_TOKENS,
                        objectIdProvider = this::cacheObjectId,
                        mapping = activeMapping,
                )

        return buildJsonObject {
            put("thread", thread.name())
            put("frame_index", frameIndex)
            put("variable_path", variablePath)
            put("depth", depth)
            put("value", inspected["value"] ?: JsonNull)
            put(
                    "token_usage_estimate",
                    inspected["token_usage_estimate"] ?: JsonPrimitive(0),
            )
            put("truncated", inspected["truncated"] ?: JsonPrimitive(false))
        }
    }

    fun evaluate(
            threadName: String,
            frameIndex: Int,
            expression: String,
    ): JsonElement {
        if (threadName.isBlank()) {
            throw RpcException(INVALID_PARAMS, "thread_name must not be blank")
        }
        if (frameIndex < 0) {
            throw RpcException(INVALID_PARAMS, "frame_index must be >= 0")
        }
        val trimmedExpression = expression.trim()
        if (trimmedExpression.isEmpty()) {
            throw RpcException(INVALID_PARAMS, "expression must not be blank")
        }

        val machine = requireAttachedMachine()
        val thread = resolveThread(machine, threadName)
        val frame = resolveFrame(thread, frameIndex)

        val result: JsonObject =
                if (trimmedExpression.endsWith(".toString()")) {
                    val targetPath = trimmedExpression.removeSuffix(".toString()").trim()
                    if (targetPath.isEmpty()) {
                        throw RpcException(INVALID_PARAMS, "toString() target must not be empty")
                    }
                    val value = resolveValuePath(frame, targetPath)
                    val text = renderToString(thread, value)
                    buildJsonObject {
                        put("value", JsonPrimitive(text))
                        put("token_usage_estimate", JsonPrimitive(estimateTokenUsage(text.length)))
                        put("truncated", JsonPrimitive(false))
                    }
                } else {
                    if (trimmedExpression.contains("(") || trimmedExpression.contains(")")) {
                        throw RpcException(
                                INVALID_PARAMS,
                                "$ERR_EVAL_UNSUPPORTED: only field access and toString() are supported",
                        )
                    }
                    val value = resolveValuePath(frame, trimmedExpression)
                    val activeMapping = mapping
                    inspector.inspectValue(
                            value = value,
                            depth = 1,
                            tokenBudget = TokenBudget.DEFAULT_MAX_TOKENS,
                            objectIdProvider = this::cacheObjectId,
                            mapping = activeMapping,
                    )
                }

        return buildJsonObject {
            put("thread", thread.name())
            put("frame_index", frameIndex)
            put("expression", trimmedExpression)
            put("result", result["value"] ?: JsonNull)
            put(
                    "token_usage_estimate",
                    result["token_usage_estimate"] ?: JsonPrimitive(0),
            )
            put("truncated", result["truncated"] ?: JsonPrimitive(false))
        }
    }

    private fun performStep(
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

        val machine = requireAttachedMachine()
        val thread = resolveThread(machine, threadName)

        synchronized(stateLock) {
            if (activeStep != null) {
                throw RpcException(INVALID_REQUEST, "Another step command is already in progress")
            }
        }

        if (!thread.isSuspended) {
            try {
                thread.suspend()
            } catch (e: Exception) {
                throw RpcException(
                        INTERNAL_ERROR,
                        "Failed to suspend thread: ${e.message ?: "unknown"}"
                )
            }
        }
        markThreadSuspended(thread)

        clearExistingStepRequests(machine, thread)

        val request =
                machine.eventRequestManager()
                        .createStepRequest(
                                thread,
                                StepRequest.STEP_LINE,
                                depth,
                        )
                        .apply {
                            addCountFilter(1)
                            setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                            putProperty("step_action", action)
                            enable()
                        }

        val completion = CompletableFuture<JsonObject>()
        synchronized(stateLock) {
            activeStep =
                    PendingStep(
                            action = action,
                            threadName = thread.name(),
                            request = request,
                            completion = completion,
                    )
            invalidateObjectCacheLocked()
        }

        try {
            thread.resume()
        } catch (e: Exception) {
            clearStepRequest(machine, request)
            synchronized(stateLock) {
                if (activeStep?.request == request) {
                    activeStep = null
                }
            }
            throw RpcException(
                    INTERNAL_ERROR,
                    "Failed to resume thread for step: ${e.message ?: "unknown"}"
            )
        }

        return try {
            completion.get((timeoutSeconds * 1000).toLong(), TimeUnit.MILLISECONDS)
        } catch (_: TimeoutException) {
            clearStepRequest(machine, request)
            synchronized(stateLock) {
                if (activeStep?.request == request) {
                    activeStep = null
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
            synchronized(stateLock) {
                if (activeStep?.request == request) {
                    activeStep = null
                }
            }
            throw RpcException(INTERNAL_ERROR, "Step failed: ${e.message ?: "unknown"}")
        }
    }

    private fun requireAttachedMachine(): VirtualMachine {
        if (disconnected) {
            throw RpcException(
                    INVALID_REQUEST,
                    "VM is disconnected: ${disconnectReason ?: "unknown"}"
            )
        }
        return vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")
    }

    private fun resolveThread(machine: VirtualMachine, threadName: String): ThreadReference {
        val threads =
                try {
                    machine.allThreads()
                } catch (e: Exception) {
                    throw RpcException(
                            INTERNAL_ERROR,
                            "Failed to list threads: ${e.message ?: "unknown"}"
                    )
                }
        return threads.firstOrNull { it.name() == threadName }
                ?: throw RpcException(INVALID_REQUEST, "Thread not found: $threadName")
    }

    private fun startEventLoop(machine: VirtualMachine) {
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
                                                    if (!handleBreakpointEvent(event)) {
                                                        shouldResumeSet = false
                                                    }
                                                }
                                                is ClassPrepareEvent ->
                                                        handleClassPrepareEvent(machine, event)
                                                is ExceptionEvent -> {
                                                    if (!handleExceptionEvent(event)) {
                                                        shouldResumeSet = false
                                                    }
                                                }
                                                is StepEvent -> {
                                                    if (!handleStepEvent(machine, event)) {
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
                                                // Ignore resume failures during
                                                // shutdown/disconnect.
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
                        "jdi-event-loop"
                )
        thread.isDaemon = true
        thread.start()
        eventThread = thread
    }

    private fun stopEventLoop() {
        eventThread?.interrupt()
        eventThread?.join(2000)
        eventThread = null
    }

    private fun handleDisconnect(reason: String) {
        log("vm disconnected: $reason")
        disconnected = true
        val normalizedReason = normalizeDisconnectReason(reason)
        disconnectReason = normalizedReason
        val pending =
                synchronized(stateLock) {
                    val current = activeStep
                    activeStep = null
                    suspendedAtMs.clear()
                    invalidateObjectCacheLocked()
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

        val notification = buildJsonObject {
            put("jsonrpc", "2.0")
            // No id = notification
            put("method", "event")
            put(
                    "params",
                    buildJsonObject {
                        put("type", "vm_disconnected")
                        put("reason", normalizedReason)
                        put("detail", reason)
                    }
            )
        }
        try {
            notificationEmitter(notification)
        } catch (_: Exception) {
            // Best effort
        }
    }

    private fun handleClassPrepareEvent(machine: VirtualMachine, event: ClassPrepareEvent) {
        // Also check for deferred exception breakpoints.
        handleClassPrepareForExceptionBreakpoints(machine, event)

        val className = event.referenceType().name()
        val pendingIds =
                synchronized(stateLock) {
                    breakpoints.values
                            .filter {
                                it.status == "pending" &&
                                        classPatternMatches(className, it.classPattern)
                            }
                            .map { it.id }
                }

        if (pendingIds.isEmpty()) {
            return
        }

        for (id in pendingIds) {
            val state = synchronized(stateLock) { breakpoints[id] } ?: continue
            val location =
                    findLocationOnType(event.referenceType() as? ClassType, state.line) ?: continue
            val request = createEnabledBreakpoint(machine, location, id)
            val locationText = formatLocation(location)

            synchronized(stateLock) {
                val current = breakpoints[id] ?: return@synchronized
                current.status = "set"
                current.location = locationText
                current.request = request
                current.prepareRequest?.let {
                    try {
                        machine.eventRequestManager().deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup.
                    }
                }
                current.prepareRequest = null
            }

            emitEvent(
                    type = "breakpoint_resolved",
                    extraParams =
                            buildJsonObject {
                                put("breakpoint_id", id)
                                put("location", locationText)
                            },
            )
        }
    }

    private fun handleClassPrepareForExceptionBreakpoints(
            machine: VirtualMachine,
            event: ClassPrepareEvent,
    ) {
        val className = event.referenceType().name()
        val pendingIds =
                synchronized(stateLock) {
                    exceptionBreakpoints.values
                            .filter {
                                it.status == "pending" &&
                                        classPatternMatches(className, it.classPattern)
                            }
                            .map { it.id }
                }

        if (pendingIds.isEmpty()) return

        for (id in pendingIds) {
            val state = synchronized(stateLock) { exceptionBreakpoints[id] } ?: continue
            val refType = event.referenceType()
            val exReq =
                    machine.eventRequestManager()
                            .createExceptionRequest(
                                    refType,
                                    state.caught,
                                    state.uncaught,
                            )
                            .apply {
                                setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                                putProperty("breakpoint_id", id)
                                enable()
                            }

            synchronized(stateLock) {
                val current = exceptionBreakpoints[id] ?: return@synchronized
                current.status = "set"
                current.request = exReq
                current.prepareRequest?.let {
                    try {
                        machine.eventRequestManager().deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup
                    }
                }
                current.prepareRequest = null
            }

            emitEvent(
                    type = "exception_breakpoint_resolved",
                    extraParams =
                            buildJsonObject {
                                put("breakpoint_id", id)
                                put("class_pattern", className)
                            },
            )
        }
    }

    private fun handleExceptionEvent(event: ExceptionEvent): Boolean {
        val request = event.request() as? ExceptionRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val thread = event.thread()
        val exceptionRef = event.exception()

        // If there's no matching breakpoint ID, ignore.
        if (requestId == null) return true

        val exists = synchronized(stateLock) { exceptionBreakpoints.containsKey(requestId) }
        if (!exists) return true

        markThreadSuspended(thread)

        val exceptionClass =
                try {
                    exceptionRef.referenceType().name()
                } catch (_: Exception) {
                    "<unknown>"
                }

        val exceptionMessage =
                try {
                    val msgField = exceptionRef.referenceType().fieldByName("detailMessage")
                    if (msgField != null) {
                        val msgValue = exceptionRef.getValue(msgField)
                        (msgValue as? StringReference)?.value()
                    } else {
                        null
                    }
                } catch (_: Exception) {
                    null
                }

        val throwLocation = formatLocation(event.location())
        val catchLocation = event.catchLocation()?.let { formatLocation(it) }

        val stopped = buildStoppedPayload(thread, event.location())

        emitEvent(
                type = "exception_hit",
                extraParams =
                        buildJsonObject {
                            put("breakpoint_id", requestId)
                            put("exception_class", exceptionClass)
                            if (exceptionMessage != null) {
                                put("exception_message", exceptionMessage)
                            }
                            put("throw_location", throwLocation)
                            if (catchLocation != null) {
                                put("catch_location", catchLocation)
                            } else {
                                put("catch_location", JsonNull)
                            }
                            for ((key, value) in stopped) {
                                put(key, value)
                            }
                        },
        )

        // Keep thread suspended for inspection.
        return false
    }

    private fun handleBreakpointEvent(event: BreakpointEvent): Boolean {
        val request = event.request() as? BreakpointRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val locationText = formatLocation(event.location())
        val thread = event.thread()

        // Fetch condition and logMessage together.
        val (condition, logMessage) =
                if (requestId != null) {
                    synchronized(stateLock) {
                        val bp = breakpoints[requestId]
                        Pair(bp?.condition, bp?.logMessage)
                    }
                } else {
                    Pair(null, null)
                }

        if (condition != null && condition.isNotBlank()) {
            val conditionResult = evaluateCondition(thread, condition)
            when (conditionResult) {
                ConditionResult.FALSE -> {
                    // Condition is false — auto-resume, don't emit event.
                    return true
                }
                is ConditionResult.ERROR -> {
                    // Condition evaluation failed — emit error event and auto-resume.
                    emitEvent(
                            type = "breakpoint_condition_error",
                            extraParams =
                                    buildJsonObject {
                                        if (requestId != null) {
                                            put("breakpoint_id", requestId)
                                        }
                                        put("condition", condition)
                                        put("error", conditionResult.message)
                                        put("location", locationText)
                                    },
                    )
                    return true
                }
                ConditionResult.TRUE -> {
                    // Condition is true — proceed with normal breakpoint hit.
                }
            }
        }

        // Logpoint: log the message and auto-resume without suspending.
        if (logMessage != null && logMessage.isNotBlank()) {
            val hitCount =
                    if (requestId != null) {
                        synchronized(stateLock) {
                            val bp = breakpoints[requestId]
                            if (bp != null) {
                                bp.hitCount += 1
                                bp.location = locationText
                                bp.hitCount
                            } else {
                                1L
                            }
                        }
                    } else {
                        1L
                    }

            val resolvedMessage = evaluateLogMessage(thread, logMessage, hitCount)

            emitEvent(
                    type = "logpoint_hit",
                    extraParams =
                            buildJsonObject {
                                if (requestId != null) {
                                    put("breakpoint_id", requestId)
                                }
                                put("message", resolvedMessage)
                                put("hit_count", hitCount)
                                put("location", locationText)
                                put("thread", thread.name())
                            },
            )

            // Auto-resume — don't keep thread suspended.
            return true
        }

        val stopped = buildStoppedPayload(thread, event.location())
        markThreadSuspended(thread)

        if (requestId != null) {
            synchronized(stateLock) { breakpoints[requestId]?.location = locationText }
        }

        emitEvent(
                type = "breakpoint_hit",
                extraParams =
                        buildJsonObject {
                            if (requestId != null) {
                                put("breakpoint_id", requestId)
                            }
                            if (condition != null) {
                                put("condition", condition)
                            }
                            for ((key, value) in stopped) {
                                put(key, value)
                            }
                        },
        )

        // Keep thread suspended at breakpoint for step/inspect flows.
        return false
    }

    /** Result of evaluating a breakpoint condition expression. */
    private sealed class ConditionResult {
        data object TRUE : ConditionResult()
        data object FALSE : ConditionResult()
        data class ERROR(val message: String) : ConditionResult()
    }

    /**
     * Evaluate a condition expression on the given thread's top frame. Returns TRUE if the value is
     * truthy, FALSE if falsy, or ERROR if evaluation fails.
     */
    private fun evaluateCondition(thread: ThreadReference, condition: String): ConditionResult {
        return try {
            val frame = thread.frame(0)
            val value = resolveValuePath(frame, condition.trim())
            if (isValueTruthy(value)) ConditionResult.TRUE else ConditionResult.FALSE
        } catch (e: Exception) {
            ConditionResult.ERROR(e.message ?: "condition evaluation failed")
        }
    }

    /** Check if a JDI Value is "truthy" (non-null, non-false, non-zero). */
    private fun isValueTruthy(value: Value?): Boolean {
        if (value == null) return false
        return when (value) {
            is BooleanValue -> value.value()
            is ByteValue -> value.value().toInt() != 0
            is ShortValue -> value.value().toInt() != 0
            is IntegerValue -> value.value() != 0
            is LongValue -> value.value() != 0L
            is FloatValue -> value.value() != 0.0f
            is DoubleValue -> value.value() != 0.0
            is CharValue -> value.value() != '\u0000'
            else -> true // Non-null object references are truthy.
        }
    }

    /**
     * Evaluate a log message template, resolving `{expr}` placeholders.
     *
     * Placeholders:
     * - `{hitCount}` → the current hit count for this breakpoint
     * - `{varName}` or `{obj.field}` → resolved via [resolveValuePath] + [renderToString]
     *
     * Unresolvable placeholders are replaced with `<error: message>`.
     */
    private fun evaluateLogMessage(
            thread: ThreadReference,
            template: String,
            hitCount: Long,
    ): String {
        val pattern = Regex("""\{([^}]+)}""")
        return pattern.replace(template) { match ->
            val expr = match.groupValues[1].trim()
            when (expr) {
                "hitCount" -> hitCount.toString()
                else -> {
                    try {
                        val frame = thread.frame(0)
                        val value = resolveValuePath(frame, expr)
                        renderToString(thread, value)
                    } catch (e: Exception) {
                        "<error: ${e.message ?: "unknown"}>"
                    }
                }
            }
        }
    }

    private fun handleStepEvent(machine: VirtualMachine, event: StepEvent): Boolean {
        val stepRequest = event.request() as? StepRequest ?: return true

        val pending =
                synchronized(stateLock) {
                    val current = activeStep
                    if (current == null || current.request != stepRequest) {
                        null
                    } else {
                        activeStep = null
                        current
                    }
                }

        if (pending == null) {
            clearStepRequest(machine, stepRequest)
            return true
        }

        clearStepRequest(machine, stepRequest)
        val payload = buildStoppedPayload(event.thread(), event.location())
        markThreadSuspended(event.thread())
        pending.completion.complete(payload)

        // Keep thread suspended on the new line for follow-up step/inspect commands.
        return false
    }

    private fun buildStoppedPayload(
            thread: ThreadReference,
            fallbackLocation: Location
    ): JsonObject {
        val frames =
                try {
                    thread.frames()
                } catch (_: Exception) {
                    emptyList()
                }
        val frameLocations = frames.map { it.location() }
        val selection =
                if (frameLocations.isEmpty()) {
                    FrameFilter.Selection(selectedIndex = 0, filteredCount = 0)
                } else {
                    FrameFilter.selectPrimaryFrame(frameLocations)
                }
        val selectedIndex = selection.selectedIndex.coerceIn(0, (frames.size - 1).coerceAtLeast(0))
        val selectedLocation = frames.getOrNull(selectedIndex)?.location() ?: fallbackLocation
        val activeMapping = mapping
        val rawClassName = selectedLocation.declaringType().name()
        val selectedMethod = selectedLocation.method()
        val selectedMethodArity =
                runCatching { selectedMethod.argumentTypeNames().size }.getOrNull()
        val mappedMethod =
                activeMapping?.deobfuscateMethod(
                        rawClassName,
                        selectedMethod.name(),
                        selectedMethodArity,
                )
                        ?: selectedMethod.name()
        val inspectedFrame =
                try {
                    inspector.inspectFrame(
                            thread = thread,
                            frameIndex = selectedIndex,
                            tokenBudget = TokenBudget.DEFAULT_MAX_TOKENS,
                            objectIdProvider = this::cacheObjectId,
                            mapping = activeMapping,
                    )
                } catch (_: Exception) {
                    buildJsonObject {
                        put("locals", JsonArray(emptyList()))
                        put("token_usage_estimate", 0)
                        put("truncated", false)
                    }
                }
        val locals = inspectedFrame["locals"] ?: JsonArray(emptyList())
        val tokenUsage = inspectedFrame["token_usage_estimate"]?.jsonPrimitive?.intOrNull ?: 0
        val truncated = inspectedFrame["truncated"]?.jsonPrimitive?.booleanOrNull ?: false

        val warning = anrWarningForThread(thread)

        return buildJsonObject {
            put("status", "stopped")
            put("location", formatLocation(selectedLocation))
            put("method", mappedMethod)
            put("thread", thread.name())
            put("locals", locals)
            put("token_usage_estimate", tokenUsage)
            put("truncated", truncated)
            if (selection.filteredCount > 0) {
                put(
                        "frame_filters",
                        buildJsonArray {
                            add(
                                    buildJsonObject {
                                        put("filtered", true)
                                        put("count", selection.filteredCount)
                                        put("reason", "coroutine_internal")
                                    }
                            )
                        }
                )
            }
            if (warning != null) {
                put("warning", warning)
            }
        }
    }

    private fun anrWarningForThread(thread: ThreadReference): String? {
        if (thread.name() != "main") {
            return null
        }
        val since = synchronized(stateLock) { suspendedAtMs[thread.uniqueID()] } ?: return null
        val elapsedSeconds = (System.currentTimeMillis() - since) / 1000.0
        if (elapsedSeconds < ANR_WARNING_SECONDS) {
            return null
        }
        return String.format(
                Locale.US,
                "main thread suspended for %.1fs — Android may trigger ANR. Consider resuming soon.",
                elapsedSeconds,
        )
    }

    private fun markThreadSuspended(thread: ThreadReference) {
        synchronized(stateLock) {
            suspendedAtMs.getOrPut(thread.uniqueID()) { System.currentTimeMillis() }
        }
    }

    private fun markThreadResumed(thread: ThreadReference) {
        synchronized(stateLock) { suspendedAtMs.remove(thread.uniqueID()) }
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

    private fun emitEvent(type: String, extraParams: JsonElement) {
        val paramsObject =
                extraParams as? JsonObject
                        ?: throw IllegalArgumentException("extraParams must be a JsonObject")

        val payload = buildJsonObject {
            put("jsonrpc", "2.0")
            put("method", "event")
            put(
                    "params",
                    buildJsonObject {
                        put("type", type)
                        for ((key, value) in paramsObject) {
                            put(key, value)
                        }
                    }
            )
        }

        try {
            notificationEmitter(payload)
        } catch (_: Exception) {
            // Best effort
        }
    }

    private fun clearBreakpointRequests(machine: VirtualMachine) {
        synchronized(stateLock) {
            val manager = machine.eventRequestManager()
            breakpoints.values.forEach { bp ->
                bp.request?.let {
                    try {
                        manager.deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup.
                    }
                }
                bp.prepareRequest?.let {
                    try {
                        manager.deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup.
                    }
                }
            }
            breakpoints.clear()
            activeStep = null
            suspendedAtMs.clear()
            invalidateObjectCacheLocked()
        }
    }

    private fun clearExceptionBreakpointRequests(machine: VirtualMachine) {
        synchronized(stateLock) {
            val manager = machine.eventRequestManager()
            exceptionBreakpoints.values.forEach { bp ->
                bp.request?.let {
                    try {
                        manager.deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup.
                    }
                }
                bp.prepareRequest?.let {
                    try {
                        manager.deleteEventRequest(it)
                    } catch (_: Exception) {
                        // Best effort cleanup.
                    }
                }
            }
            exceptionBreakpoints.clear()
        }
    }

    private fun requireThreadFrames(thread: ThreadReference): List<StackFrame> {
        if (!thread.isSuspended) {
            throw RpcException(
                    INVALID_REQUEST,
                    "$ERR_NOT_SUSPENDED: thread '${thread.name()}' is not suspended",
            )
        }
        return try {
            thread.frames()
        } catch (e: IncompatibleThreadStateException) {
            throw RpcException(
                    INVALID_REQUEST,
                    "$ERR_NOT_SUSPENDED: thread '${thread.name()}' is not suspended",
            )
        } catch (e: Exception) {
            throw RpcException(
                    INTERNAL_ERROR,
                    "Failed to read thread frames: ${e.message ?: "unknown"}"
            )
        }
    }

    private fun resolveFrame(thread: ThreadReference, frameIndex: Int): StackFrame {
        val frames = requireThreadFrames(thread)
        if (frameIndex >= frames.size) {
            throw RpcException(
                    INVALID_PARAMS,
                    "frame_index out of range: $frameIndex (frame_count=${frames.size})",
            )
        }
        return frames[frameIndex]
    }

    private fun resolveValuePath(frame: StackFrame, variablePath: String): Value? {
        val segments = variablePath.split(".").map { it.trim() }.filter { it.isNotEmpty() }
        if (segments.isEmpty()) {
            throw RpcException(INVALID_PARAMS, "variable_path must not be blank")
        }

        var current: Value? = resolveRootValue(frame, segments.first())
        for (index in 1 until segments.size) {
            val fieldName = segments[index]
            if (current == null) {
                val traversed = segments.take(index).joinToString(".")
                throw RpcException(
                        INVALID_REQUEST,
                        "Cannot access '$fieldName' on null while traversing '$traversed'",
                )
            }
            val objectRef =
                    current as? ObjectReference
                            ?: throw RpcException(
                                    INVALID_REQUEST,
                                    "Cannot access '$fieldName' on non-object value at '${segments.take(index).joinToString(".")}'",
                            )
            current = resolveFieldValue(objectRef, fieldName)
        }
        return current
    }

    private fun resolveRootValue(frame: StackFrame, root: String): Value? {
        if (root.startsWith("obj_")) {
            return resolveCachedObject(root)
        }

        val local =
                try {
                    frame.visibleVariables().firstOrNull { it.name() == root }
                } catch (_: AbsentInformationException) {
                    null
                } catch (e: Exception) {
                    throw RpcException(
                            INTERNAL_ERROR,
                            "Failed to read frame locals: ${e.message ?: "unknown"}"
                    )
                } ?: throw RpcException(INVALID_REQUEST, "Local variable not found: $root")

        return try {
            frame.getValue(local)
        } catch (e: Exception) {
            throw RpcException(
                    INTERNAL_ERROR,
                    "Failed to read local '$root': ${e.message ?: "unknown"}"
            )
        }
    }

    private fun resolveFieldValue(objectRef: ObjectReference, fieldName: String): Value? {
        val referenceType = objectRef.referenceType()
        val rawClassName = referenceType.name()
        val fields = referenceType.allFields()
        val field =
                fields.firstOrNull { it.name() == fieldName }
                        ?: run {
                            val remapped = mapping?.obfuscateField(rawClassName, fieldName)
                            if (remapped != null) {
                                fields.firstOrNull { it.name() == remapped }
                            } else {
                                null
                            }
                        }
                                ?: throw RpcException(
                                INVALID_REQUEST,
                                "Field '$fieldName' not found on ${mapping?.deobfuscateClass(rawClassName) ?: rawClassName}",
                        )
        return try {
            objectRef.getValue(field)
        } catch (e: ObjectCollectedException) {
            throw RpcException(
                    INVALID_REQUEST,
                    "$ERR_OBJECT_COLLECTED: object was collected while reading '$fieldName'",
            )
        } catch (e: Exception) {
            throw RpcException(
                    INTERNAL_ERROR,
                    "Failed to read field '$fieldName': ${e.message ?: "unknown"}"
            )
        }
    }

    private fun renderToString(thread: ThreadReference, value: Value?): String {
        if (value == null) {
            return "null"
        }
        if (value is StringReference) {
            return value.value()
        }
        if (value is PrimitiveValue) {
            return value.toString()
        }
        val objectRef = value as? ObjectReference ?: return value.toString()

        val toStringMethod =
                objectRef.referenceType().methodsByName("toString").firstOrNull {
                    it.argumentTypeNames().isEmpty()
                }
                        ?: return objectRef.toString()

        return try {
            val invoked =
                    objectRef.invokeMethod(
                            thread,
                            toStringMethod,
                            emptyList<Value>(),
                            ObjectReference.INVOKE_SINGLE_THREADED,
                    )
            when (invoked) {
                null -> "null"
                is StringReference -> invoked.value()
                else -> invoked.toString()
            }
        } catch (e: ObjectCollectedException) {
            throw RpcException(INVALID_REQUEST, "$ERR_OBJECT_COLLECTED: object no longer available")
        } catch (e: Exception) {
            throw RpcException(
                    INTERNAL_ERROR,
                    "Failed to invoke toString(): ${e.message ?: "unknown"}"
            )
        }
    }

    private fun cacheObjectId(objectRef: ObjectReference): String {
        val uniqueId = objectRef.uniqueID()
        synchronized(stateLock) {
            val existing = objectIdsByUniqueId[uniqueId]
            if (existing != null) {
                objectRefsById[existing] = objectRef
                return existing
            }

            val id = "obj_${nextObjectId++}"
            objectIdsByUniqueId[uniqueId] = id
            objectRefsById[id] = objectRef
            return id
        }
    }

    private fun resolveCachedObject(objectId: String): ObjectReference {
        synchronized(stateLock) {
            return objectRefsById[objectId]
                    ?: throw RpcException(
                            INVALID_REQUEST,
                            "$ERR_OBJECT_COLLECTED: stale object id '$objectId'",
                    )
        }
    }

    private fun invalidateObjectCacheLocked() {
        objectIdsByUniqueId.clear()
        objectRefsById.clear()
    }

    private fun estimateTokenUsage(charCount: Int): Int {
        if (charCount <= 0) {
            return 0
        }
        return (charCount + 3) / 4
    }

    private fun findLoadedLocation(
            machine: VirtualMachine,
            classPattern: String,
            line: Int
    ): Location? {
        return machine.allClasses()
                .asSequence()
                .filterIsInstance<ClassType>()
                .filter { classPatternMatches(it.name(), classPattern) }
                .mapNotNull { findLocationOnType(it, line) }
                .firstOrNull()
    }

    private fun findLocationOnType(classType: ClassType?, line: Int): Location? {
        if (classType == null) {
            return null
        }

        return try {
            classType.locationsOfLine(line).firstOrNull()
        } catch (_: AbsentInformationException) {
            null
        } catch (_: UnsupportedOperationException) {
            null
        }
    }

    private fun createEnabledBreakpoint(
            machine: VirtualMachine,
            location: Location,
            breakpointId: Int,
    ): BreakpointRequest {
        return machine.eventRequestManager().createBreakpointRequest(location).apply {
            setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
            putProperty("breakpoint_id", breakpointId)
            enable()
        }
    }

    private fun classPatternMatches(className: String, classPattern: String): Boolean {
        if (!classPattern.contains('*')) {
            return className == classPattern
        }

        val regex = classPattern.replace(".", "\\.").replace("*", ".*").toRegex()
        return regex.matches(className)
    }

    private fun formatLocation(location: Location): String {
        val rawClassName = location.declaringType().name()
        val className = mapping?.deobfuscateClass(rawClassName) ?: rawClassName
        return "$className:${location.lineNumber()}"
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
            val daemonField =
                    thread.referenceType().allFields().firstOrNull { it.name() == "daemon" }
                            ?: return false
            val value = thread.getValue(daemonField)
            (value as? BooleanValue)?.value() ?: false
        } catch (_: Exception) {
            false
        }
    }

    private fun findSocketAttachConnector(): AttachingConnector {
        val vmm = Bootstrap.virtualMachineManager()
        return vmm.attachingConnectors().firstOrNull { it.name() == "com.sun.jdi.SocketAttach" }
                ?: throw RpcException(INTERNAL_ERROR, "SocketAttach connector not found in JDK")
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
