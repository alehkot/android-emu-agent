package dev.androidemu.jdibridge

import com.sun.jdi.BooleanValue
import com.sun.jdi.ByteValue
import com.sun.jdi.CharValue
import com.sun.jdi.ClassType
import com.sun.jdi.DoubleValue
import com.sun.jdi.FloatValue
import com.sun.jdi.IntegerValue
import com.sun.jdi.Location
import com.sun.jdi.LongValue
import com.sun.jdi.ShortValue
import com.sun.jdi.StringReference
import com.sun.jdi.ThreadReference
import com.sun.jdi.Value
import com.sun.jdi.VirtualMachine
import com.sun.jdi.event.BreakpointEvent
import com.sun.jdi.event.ClassPrepareEvent
import com.sun.jdi.event.ExceptionEvent
import com.sun.jdi.request.BreakpointRequest
import com.sun.jdi.request.ClassPrepareRequest
import com.sun.jdi.request.EventRequest
import com.sun.jdi.request.ExceptionRequest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

internal class JdiBreakpointService(
    private val state: JdiSessionState,
    private val threadControlService: JdiThreadControlService,
    private val frameValueService: JdiFrameValueService,
    private val emitEvent: (String, JsonObject) -> Unit,
) {
    companion object {
        private const val ERR_CONDITION_SYNTAX = "ERR_CONDITION_SYNTAX"
    }

    fun setBreakpoint(
        machine: VirtualMachine,
        classPattern: String,
        line: Int,
        condition: String? = null,
        logMessage: String? = null,
        captureStack: Boolean = false,
        stackMaxFrames: Int = JdiSession.DEFAULT_LOGPOINT_STACK_FRAMES,
    ): JsonElement {
        if (line <= 0) {
            throw RpcException(INVALID_PARAMS, "line must be > 0")
        }
        if (stackMaxFrames <= 0) {
            throw RpcException(INVALID_PARAMS, "stack_max_frames must be > 0")
        }
        if (captureStack && logMessage.isNullOrBlank()) {
            throw RpcException(
                INVALID_PARAMS,
                "capture_stack requires a non-suspending logpoint (--log-message)",
            )
        }
        val normalizedCondition = condition?.trim()
        if (normalizedCondition != null && normalizedCondition.isEmpty()) {
            throw RpcException(INVALID_PARAMS, "$ERR_CONDITION_SYNTAX: condition must not be blank")
        }
        val compiledCondition =
            if (normalizedCondition != null) {
                try {
                    ConditionExpression.parse(normalizedCondition)
                } catch (e: ConditionSyntaxException) {
                    throw RpcException(
                        INVALID_PARAMS,
                        "$ERR_CONDITION_SYNTAX: ${e.message ?: "invalid condition"}",
                    )
                }
            } else {
                null
            }

        val breakpointId =
            synchronized(state.lock) {
                val id = state.nextBreakpointId
                state.nextBreakpointId += 1
                id
            }

        val resolvedLocation = findLoadedLocation(machine, classPattern, line)
        if (resolvedLocation != null) {
            val request = createEnabledBreakpoint(machine, resolvedLocation, breakpointId)
            val locationText = formatLocation(resolvedLocation)
            synchronized(state.lock) {
                state.breakpoints[breakpointId] =
                    BreakpointState(
                        id = breakpointId,
                        classPattern = classPattern,
                        line = line,
                        status = "set",
                        location = locationText,
                        request = request,
                        condition = normalizedCondition,
                        compiledCondition = compiledCondition,
                        logMessage = logMessage,
                        captureStack = captureStack,
                        stackMaxFrames = stackMaxFrames,
                    )
            }
            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("location", locationText)
                if (normalizedCondition != null) {
                    put("condition", normalizedCondition)
                }
                if (logMessage != null) {
                    put("log_message", logMessage)
                    put("capture_stack", captureStack)
                    put("stack_max_frames", stackMaxFrames)
                }
            }
        }

        val prepareRequest =
            machine
                .eventRequestManager()
                .createClassPrepareRequest()
                .apply {
                    addClassFilter(classPattern)
                    setSuspendPolicy(EventRequest.SUSPEND_NONE)
                    putProperty("breakpoint_id", breakpointId)
                    enable()
                }

        val resolvedAfterPrepare = findLoadedLocation(machine, classPattern, line)
        if (resolvedAfterPrepare != null) {
            val request = createEnabledBreakpoint(machine, resolvedAfterPrepare, breakpointId)
            val locationText = formatLocation(resolvedAfterPrepare)
            try {
                machine.eventRequestManager().deleteEventRequest(prepareRequest)
            } catch (_: Exception) {
                // Best effort cleanup.
            }
            synchronized(state.lock) {
                state.breakpoints[breakpointId] =
                    BreakpointState(
                        id = breakpointId,
                        classPattern = classPattern,
                        line = line,
                        status = "set",
                        location = locationText,
                        request = request,
                        condition = normalizedCondition,
                        compiledCondition = compiledCondition,
                        logMessage = logMessage,
                        captureStack = captureStack,
                        stackMaxFrames = stackMaxFrames,
                    )
            }
            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("location", locationText)
                if (normalizedCondition != null) {
                    put("condition", normalizedCondition)
                }
                if (logMessage != null) {
                    put("log_message", logMessage)
                    put("capture_stack", captureStack)
                    put("stack_max_frames", stackMaxFrames)
                }
            }
        }

        synchronized(state.lock) {
            state.breakpoints[breakpointId] =
                BreakpointState(
                    id = breakpointId,
                    classPattern = classPattern,
                    line = line,
                    status = "pending",
                    prepareRequest = prepareRequest,
                    condition = normalizedCondition,
                    compiledCondition = compiledCondition,
                    logMessage = logMessage,
                    captureStack = captureStack,
                    stackMaxFrames = stackMaxFrames,
                )
        }

        return buildJsonObject {
            put("status", "pending")
            put("breakpoint_id", breakpointId)
            put("reason", "class_not_loaded")
            put("class_pattern", classPattern)
            put("line", line)
            if (normalizedCondition != null) {
                put("condition", normalizedCondition)
            }
            if (logMessage != null) {
                put("log_message", logMessage)
                put("capture_stack", captureStack)
                put("stack_max_frames", stackMaxFrames)
            }
        }
    }

    fun removeBreakpoint(machine: VirtualMachine, breakpointId: Int): JsonElement {
        if (breakpointId <= 0) {
            throw RpcException(INVALID_PARAMS, "breakpoint_id must be > 0")
        }

        val stateEntry =
            synchronized(state.lock) { state.breakpoints.remove(breakpointId) }
                ?: throw RpcException(INVALID_REQUEST, "Unknown breakpoint_id: $breakpointId")

        val manager = machine.eventRequestManager()
        stateEntry.request?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup for stale requests
            }
        }
        stateEntry.prepareRequest?.let {
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
        val snapshot =
            synchronized(state.lock) {
                state.breakpoints.values.map {
                    BreakpointState(
                        id = it.id,
                        classPattern = it.classPattern,
                        line = it.line,
                        status = it.status,
                        location = it.location,
                        condition = it.condition,
                        logMessage = it.logMessage,
                        captureStack = it.captureStack,
                        stackMaxFrames = it.stackMaxFrames,
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
                                put("capture_stack", bp.captureStack)
                                put("stack_max_frames", bp.stackMaxFrames)
                                put("hit_count", bp.hitCount)
                            }
                        }
                    },
                ),
            )
        }
    }

    fun setExceptionBreakpoint(
        machine: VirtualMachine,
        classPattern: String,
        caught: Boolean,
        uncaught: Boolean,
    ): JsonElement {
        if (!caught && !uncaught) {
            throw RpcException(INVALID_PARAMS, "At least one of caught or uncaught must be true")
        }

        val breakpointId =
            synchronized(state.lock) {
                val id = state.nextBreakpointId
                state.nextBreakpointId += 1
                id
            }

        val refType =
            if (classPattern == "*" || classPattern.isEmpty()) {
                null
            } else {
                machine.classesByName(classPattern).firstOrNull()
            }

        val isWildcard = classPattern == "*" || classPattern.isEmpty()

        if (refType != null || isWildcard) {
            val exReq =
                machine
                    .eventRequestManager()
                    .createExceptionRequest(
                        refType,
                        caught,
                        uncaught,
                    ).apply {
                        setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                        putProperty("breakpoint_id", breakpointId)
                        enable()
                    }

            synchronized(state.lock) {
                state.exceptionBreakpoints[breakpointId] =
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

        val prepareReq =
            machine
                .eventRequestManager()
                .createClassPrepareRequest()
                .apply {
                    addClassFilter(classPattern)
                    setSuspendPolicy(EventRequest.SUSPEND_NONE)
                    putProperty("exception_breakpoint_id", breakpointId)
                    enable()
                }

        val refTypeAfterPrepare = machine.classesByName(classPattern).firstOrNull()
        if (refTypeAfterPrepare != null) {
            val exReq =
                machine
                    .eventRequestManager()
                    .createExceptionRequest(
                        refTypeAfterPrepare,
                        caught,
                        uncaught,
                    ).apply {
                        setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                        putProperty("breakpoint_id", breakpointId)
                        enable()
                    }
            try {
                machine.eventRequestManager().deleteEventRequest(prepareReq)
            } catch (_: Exception) {
                // Best effort cleanup.
            }

            synchronized(state.lock) {
                state.exceptionBreakpoints[breakpointId] =
                    ExceptionBreakpointState(
                        id = breakpointId,
                        classPattern = classPattern,
                        caught = caught,
                        uncaught = uncaught,
                        status = "set",
                        request = exReq,
                    )
            }

            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("class_pattern", classPattern)
                put("caught", caught)
                put("uncaught", uncaught)
            }
        }

        synchronized(state.lock) {
            state.exceptionBreakpoints[breakpointId] =
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

    fun removeExceptionBreakpoint(machine: VirtualMachine, breakpointId: Int): JsonElement {
        if (breakpointId <= 0) {
            throw RpcException(INVALID_PARAMS, "breakpoint_id must be > 0")
        }

        val stateEntry =
            synchronized(state.lock) { state.exceptionBreakpoints.remove(breakpointId) }
                ?: throw RpcException(INVALID_REQUEST, "Unknown exception breakpoint_id: $breakpointId")

        val manager = machine.eventRequestManager()
        stateEntry.request?.let {
            try {
                manager.deleteEventRequest(it)
            } catch (_: Exception) {
                // Best effort cleanup
            }
        }
        stateEntry.prepareRequest?.let {
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
        val snapshot =
            synchronized(state.lock) {
                state.exceptionBreakpoints.values.map {
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
                    },
                ),
            )
        }
    }

    fun handleClassPrepareEvent(machine: VirtualMachine, event: ClassPrepareEvent) {
        handleClassPrepareForExceptionBreakpoints(machine, event)

        val className = event.referenceType().name()
        val pendingIds =
            synchronized(state.lock) {
                state.breakpoints.values
                    .filter { it.status == "pending" && classPatternMatches(className, it.classPattern) }
                    .map { it.id }
            }

        if (pendingIds.isEmpty()) {
            return
        }

        for (id in pendingIds) {
            val stateEntry = synchronized(state.lock) { state.breakpoints[id] } ?: continue
            val location = findLocationOnType(event.referenceType() as? ClassType, stateEntry.line) ?: continue
            val request = createEnabledBreakpoint(machine, location, id)
            val locationText = formatLocation(location)

            synchronized(state.lock) {
                val current = state.breakpoints[id] ?: return@synchronized
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
                "breakpoint_resolved",
                buildJsonObject {
                    put("breakpoint_id", id)
                    put("location", locationText)
                },
            )
        }
    }

    fun handleExceptionEvent(event: ExceptionEvent): Boolean {
        val request = event.request() as? ExceptionRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val thread = event.thread()
        val exceptionRef = event.exception()

        if (requestId == null) return true

        val exists = synchronized(state.lock) { state.exceptionBreakpoints.containsKey(requestId) }
        if (!exists) return true

        threadControlService.markThreadSuspended(thread)

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

        val stopped = frameValueService.buildStoppedPayload(thread, event.location())

        emitEvent(
            "exception_hit",
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

        return false
    }

    fun handleBreakpointEvent(event: BreakpointEvent): Boolean {
        val request = event.request() as? BreakpointRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val locationText = formatLocation(event.location())
        val thread = event.thread()

        val breakpointState =
            if (requestId != null) {
                synchronized(state.lock) { state.breakpoints[requestId] }
            } else {
                null
            }
        val condition = breakpointState?.condition
        val compiledCondition = breakpointState?.compiledCondition
        val logMessage = breakpointState?.logMessage
        val captureStack = breakpointState?.captureStack ?: false
        val stackMaxFrames = breakpointState?.stackMaxFrames ?: JdiSession.DEFAULT_LOGPOINT_STACK_FRAMES

        if (condition != null && condition.isNotBlank()) {
            val conditionExpression =
                compiledCondition ?: runCatching { ConditionExpression.parse(condition) }.getOrNull()
            if (conditionExpression == null) {
                emitEvent(
                    "breakpoint_condition_error",
                    buildJsonObject {
                        if (requestId != null) {
                            put("breakpoint_id", requestId)
                        }
                        put("condition", condition)
                        put("error", "condition expression is unavailable")
                        put("location", locationText)
                    },
                )
                return true
            }
            val conditionResult = evaluateCondition(thread, conditionExpression)
            when (conditionResult) {
                ConditionResult.FALSE -> {
                    return true
                }
                is ConditionResult.ERROR -> {
                    emitEvent(
                        "breakpoint_condition_error",
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
                    // proceed
                }
            }
        }

        if (logMessage != null && logMessage.isNotBlank()) {
            val hitCount =
                if (requestId != null) {
                    synchronized(state.lock) {
                        val bp = state.breakpoints[requestId]
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

            val resolvedMessage = frameValueService.evaluateLogMessage(thread, logMessage, hitCount)
            val timestampMs = System.currentTimeMillis()
            val stackPayload =
                if (captureStack) {
                    frameValueService.buildLogpointStack(thread, stackMaxFrames)
                } else {
                    null
                }

            emitEvent(
                "logpoint_hit",
                buildJsonObject {
                    if (requestId != null) {
                        put("breakpoint_id", requestId)
                    }
                    put("message", resolvedMessage)
                    put("hit_count", hitCount)
                    put("location", locationText)
                    put("thread", thread.name())
                    put("timestamp_ms", timestampMs)
                    if (stackPayload != null) {
                        put("stack", stackPayload)
                    }
                },
            )

            return true
        }

        val stopped = frameValueService.buildStoppedPayload(thread, event.location())
        threadControlService.markThreadSuspended(thread)

        if (requestId != null) {
            synchronized(state.lock) { state.breakpoints[requestId]?.location = locationText }
        }

        emitEvent(
            "breakpoint_hit",
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

        return false
    }

    fun clearBreakpointRequests(machine: VirtualMachine) {
        synchronized(state.lock) {
            val manager = machine.eventRequestManager()
            state.breakpoints.values.forEach { bp ->
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
            state.breakpoints.clear()
            state.activeStep = null
            state.suspendedAtMs.clear()
            frameValueService.invalidateObjectCacheLocked()
        }
    }

    fun clearExceptionBreakpointRequests(machine: VirtualMachine) {
        synchronized(state.lock) {
            val manager = machine.eventRequestManager()
            state.exceptionBreakpoints.values.forEach { bp ->
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
            state.exceptionBreakpoints.clear()
        }
    }

    private fun handleClassPrepareForExceptionBreakpoints(
        machine: VirtualMachine,
        event: ClassPrepareEvent,
    ) {
        val className = event.referenceType().name()
        val pendingIds =
            synchronized(state.lock) {
                state.exceptionBreakpoints.values
                    .filter { it.status == "pending" && classPatternMatches(className, it.classPattern) }
                    .map { it.id }
            }

        if (pendingIds.isEmpty()) return

        for (id in pendingIds) {
            val stateEntry = synchronized(state.lock) { state.exceptionBreakpoints[id] } ?: continue
            val refType = event.referenceType()
            val exReq =
                machine
                    .eventRequestManager()
                    .createExceptionRequest(
                        refType,
                        stateEntry.caught,
                        stateEntry.uncaught,
                    ).apply {
                        setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD)
                        putProperty("breakpoint_id", id)
                        enable()
                    }

            synchronized(state.lock) {
                val current = state.exceptionBreakpoints[id] ?: return@synchronized
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
                "exception_breakpoint_resolved",
                buildJsonObject {
                    put("breakpoint_id", id)
                    put("class_pattern", className)
                },
            )
        }
    }

    private sealed class ConditionResult {
        data object TRUE : ConditionResult()
        data object FALSE : ConditionResult()
        data class ERROR(val message: String) : ConditionResult()
    }

    private fun evaluateCondition(
        thread: ThreadReference,
        condition: ConditionExpression,
    ): ConditionResult {
        return try {
            val frame = thread.frame(0)
            val matched =
                condition.evaluate { path ->
                    toConditionRuntimeValue(frameValueService.resolveValuePath(frame, path))
                }
            if (matched) ConditionResult.TRUE else ConditionResult.FALSE
        } catch (e: Exception) {
            ConditionResult.ERROR(e.message ?: "condition evaluation failed")
        }
    }

    private fun toConditionRuntimeValue(value: Value?): ConditionExpression.RuntimeValue {
        if (value == null) {
            return ConditionExpression.RuntimeValue.Null
        }
        return when (value) {
            is BooleanValue -> ConditionExpression.RuntimeValue.Bool(value.value())
            is ByteValue -> ConditionExpression.RuntimeValue.Number(value.value().toDouble())
            is ShortValue -> ConditionExpression.RuntimeValue.Number(value.value().toDouble())
            is IntegerValue -> ConditionExpression.RuntimeValue.Number(value.value().toDouble())
            is LongValue -> ConditionExpression.RuntimeValue.Number(value.value().toDouble())
            is FloatValue -> ConditionExpression.RuntimeValue.Number(value.value().toDouble())
            is DoubleValue -> ConditionExpression.RuntimeValue.Number(value.value())
            is CharValue -> ConditionExpression.RuntimeValue.Number(value.value().code.toDouble())
            is StringReference -> ConditionExpression.RuntimeValue.Text(value.value())
            else -> {
                val typeName = runCatching { value.type().name() }.getOrNull()
                ConditionExpression.RuntimeValue.Object(typeName)
            }
        }
    }

    private fun findLoadedLocation(
        machine: VirtualMachine,
        classPattern: String,
        line: Int,
    ): Location? {
        return machine
            .allClasses()
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
        } catch (_: Exception) {
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
        val className = state.mapping?.deobfuscateClass(rawClassName) ?: rawClassName
        return "$className:${location.lineNumber()}"
    }
}
