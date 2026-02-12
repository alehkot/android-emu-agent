package dev.androidemu.jdibridge

import com.sun.jdi.AbsentInformationException
import com.sun.jdi.BooleanValue
import com.sun.jdi.Bootstrap
import com.sun.jdi.ClassType
import com.sun.jdi.Location
import com.sun.jdi.StackFrame
import com.sun.jdi.StringReference
import com.sun.jdi.ThreadReference
import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.Value
import com.sun.jdi.VirtualMachine
import com.sun.jdi.connect.AttachingConnector
import com.sun.jdi.event.BreakpointEvent
import com.sun.jdi.event.ClassPrepareEvent
import com.sun.jdi.event.VMDeathEvent
import com.sun.jdi.event.VMDisconnectEvent
import com.sun.jdi.request.BreakpointRequest
import com.sun.jdi.request.ClassPrepareRequest
import com.sun.jdi.request.EventRequest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Manages a single JDI connection to a target JVM.
 *
 * Thread safety: [status] and command handlers may run on the main RPC thread while
 * the event loop consumes JDI events on a background daemon thread.
 */
class JdiSession(
    private val notificationEmitter: (JsonElement) -> Unit,
) {
    private data class BreakpointState(
        val id: Int,
        val classPattern: String,
        val line: Int,
        var status: String,
        var location: String? = null,
        var request: BreakpointRequest? = null,
        var prepareRequest: ClassPrepareRequest? = null,
    )

    @Volatile
    private var vm: VirtualMachine? = null

    @Volatile
    private var eventThread: Thread? = null

    @Volatile
    private var disconnected = false

    @Volatile
    private var disconnectReason: String? = null

    private val stateLock = Any()
    private val breakpoints = linkedMapOf<Int, BreakpointState>()
    private var nextBreakpointId = 1

    val isAttached: Boolean get() = vm != null && !disconnected

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
        val machine = try {
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
        try {
            machine.dispose()
        } catch (_: Exception) {
            // VM may already be gone
        }
        vm = null
        disconnected = false
        disconnectReason = null

        return buildJsonObject {
            put("status", "detached")
        }
    }

    fun status(): JsonElement {
        val machine = vm
        if (machine == null) {
            return buildJsonObject {
                put("status", "not_attached")
            }
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

    fun setBreakpoint(classPattern: String, line: Int): JsonElement {
        if (line <= 0) {
            throw RpcException(INVALID_PARAMS, "line must be > 0")
        }

        val machine = requireAttachedMachine()
        val breakpointId = synchronized(stateLock) {
            val id = nextBreakpointId
            nextBreakpointId += 1
            id
        }

        val resolvedLocation = findLoadedLocation(machine, classPattern, line)
        if (resolvedLocation != null) {
            val request = createEnabledBreakpoint(machine, resolvedLocation, breakpointId)
            val locationText = formatLocation(resolvedLocation)
            synchronized(stateLock) {
                breakpoints[breakpointId] = BreakpointState(
                    id = breakpointId,
                    classPattern = classPattern,
                    line = line,
                    status = "set",
                    location = locationText,
                    request = request,
                )
            }
            return buildJsonObject {
                put("status", "set")
                put("breakpoint_id", breakpointId)
                put("location", locationText)
            }
        }

        val prepareRequest = machine.eventRequestManager().createClassPrepareRequest().apply {
            addClassFilter(classPattern)
            setSuspendPolicy(EventRequest.SUSPEND_NONE)
            putProperty("breakpoint_id", breakpointId)
            enable()
        }

        synchronized(stateLock) {
            breakpoints[breakpointId] = BreakpointState(
                id = breakpointId,
                classPattern = classPattern,
                line = line,
                status = "pending",
                prepareRequest = prepareRequest,
            )
        }

        return buildJsonObject {
            put("status", "pending")
            put("breakpoint_id", breakpointId)
            put("reason", "class_not_loaded")
            put("class_pattern", classPattern)
            put("line", line)
        }
    }

    fun removeBreakpoint(breakpointId: Int): JsonElement {
        if (breakpointId <= 0) {
            throw RpcException(INVALID_PARAMS, "breakpoint_id must be > 0")
        }

        val machine = requireAttachedMachine()
        val state = synchronized(stateLock) {
            breakpoints.remove(breakpointId)
        } ?: throw RpcException(INVALID_REQUEST, "Unknown breakpoint_id: $breakpointId")

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
        val snapshot = synchronized(stateLock) {
            breakpoints.values.map {
                BreakpointState(
                    id = it.id,
                    classPattern = it.classPattern,
                    line = it.line,
                    status = it.status,
                    location = it.location,
                )
            }
        }

        return buildJsonObject {
            put("count", snapshot.size)
            put("breakpoints", JsonArray(snapshot.map { bp ->
                buildJsonObject {
                    put("breakpoint_id", bp.id)
                    put("class_pattern", bp.classPattern)
                    put("line", bp.line)
                    put("status", bp.status)
                    if (bp.location != null) {
                        put("location", bp.location)
                    }
                }
            }))
        }
    }

    fun listThreads(includeDaemon: Boolean, maxThreads: Int): JsonElement {
        if (maxThreads <= 0) {
            throw RpcException(INVALID_PARAMS, "max_threads must be > 0")
        }

        val machine = requireAttachedMachine()
        val allThreads = try {
            machine.allThreads()
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to list threads: ${e.message}")
        }

        val filtered = if (includeDaemon) {
            allThreads
        } else {
            allThreads.filter { !isDaemonThread(it) }
        }

        val total = filtered.size
        val limited = filtered.take(maxThreads)

        return buildJsonObject {
            put("threads", JsonArray(limited.map { thread ->
                buildJsonObject {
                    put("name", thread.name())
                    put("state", mapThreadState(thread))
                    put("daemon", isDaemonThread(thread))
                }
            }))
            put("total_threads", total)
            put("shown_threads", limited.size)
            put("truncated", total > limited.size)
            put("include_daemon", includeDaemon)
            put("max_threads", maxThreads)
        }
    }

    private fun requireAttachedMachine(): VirtualMachine {
        if (disconnected) {
            throw RpcException(INVALID_REQUEST, "VM is disconnected: ${disconnectReason ?: "unknown"}")
        }
        return vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")
    }

    private fun startEventLoop(machine: VirtualMachine) {
        val thread = Thread({
            try {
                val eventQueue = machine.eventQueue()
                while (!Thread.currentThread().isInterrupted) {
                    val eventSet = try {
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
                    try {
                        for (event in eventSet) {
                            when (event) {
                                is BreakpointEvent -> handleBreakpointEvent(machine, event)
                                is ClassPrepareEvent -> handleClassPrepareEvent(machine, event)
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
                        try {
                            eventSet.resume()
                        } catch (_: Exception) {
                            // Ignore resume failures during shutdown/disconnect.
                        }
                    }

                    if (shouldStop) {
                        break
                    }
                }
            } catch (_: Exception) {
                // Outer safety catch.
            }
        }, "jdi-event-loop")
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

        val notification = buildJsonObject {
            put("jsonrpc", "2.0")
            // No id = notification
            put("method", "event")
            put("params", buildJsonObject {
                put("type", "vm_disconnected")
                put("reason", normalizedReason)
                put("detail", reason)
            })
        }
        try {
            notificationEmitter(notification)
        } catch (_: Exception) {
            // Best effort
        }
    }

    private fun handleClassPrepareEvent(machine: VirtualMachine, event: ClassPrepareEvent) {
        val className = event.referenceType().name()
        val pendingIds = synchronized(stateLock) {
            breakpoints.values
                .filter { it.status == "pending" && classPatternMatches(className, it.classPattern) }
                .map { it.id }
        }

        if (pendingIds.isEmpty()) {
            return
        }

        for (id in pendingIds) {
            val state = synchronized(stateLock) { breakpoints[id] } ?: continue
            val location = findLocationOnType(event.referenceType() as? ClassType, state.line) ?: continue
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
                extraParams = buildJsonObject {
                    put("breakpoint_id", id)
                    put("location", locationText)
                },
            )
        }
    }

    private fun handleBreakpointEvent(machine: VirtualMachine, event: BreakpointEvent) {
        val request = event.request() as? BreakpointRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val locationText = formatLocation(event.location())
        val locals = safeTopFrameLocals(event.thread())

        if (requestId != null) {
            synchronized(stateLock) {
                breakpoints[requestId]?.location = locationText
            }
        }

        emitEvent(
            type = "breakpoint_hit",
            extraParams = buildJsonObject {
                if (requestId != null) {
                    put("breakpoint_id", requestId)
                }
                put("thread", event.thread().name())
                put("location", locationText)
                put("locals", locals)
            },
        )

        // Keep VM running unless client asks to suspend in a later milestone.
        try {
            machine.resume()
        } catch (_: Exception) {
            // Ignore resume failures during disconnect.
        }
    }

    private fun emitEvent(type: String, extraParams: JsonElement) {
        val paramsObject = extraParams as? kotlinx.serialization.json.JsonObject
            ?: throw IllegalArgumentException("extraParams must be a JsonObject")

        val payload = buildJsonObject {
            put("jsonrpc", "2.0")
            put("method", "event")
            put("params", buildJsonObject {
                put("type", type)
                for ((key, value) in paramsObject) {
                    put(key, value)
                }
            })
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
        }
    }

    private fun findLoadedLocation(machine: VirtualMachine, classPattern: String, line: Int): Location? {
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

    private fun safeTopFrameLocals(thread: ThreadReference): JsonArray {
        if (!thread.isSuspended) {
            return JsonArray(emptyList())
        }

        val frame = try {
            thread.frame(0)
        } catch (_: Exception) {
            return JsonArray(emptyList())
        }

        return serializeLocals(frame)
    }

    private fun serializeLocals(frame: StackFrame): JsonArray {
        val maxLocals = 10
        val maxChars = 512
        var remainingChars = maxChars
        var emittedCount = 0

        val variables = try {
            frame.visibleVariables()
        } catch (_: AbsentInformationException) {
            return JsonArray(emptyList())
        } catch (_: Exception) {
            return JsonArray(emptyList())
        }

        return buildJsonArray {
            for (variable in variables) {
                if (emittedCount >= maxLocals || remainingChars <= 0) {
                    break
                }

                val value = try {
                    frame.getValue(variable)
                } catch (_: Exception) {
                    null
                }
                val rendered = renderValue(value)
                remainingChars -= rendered.length

                add(buildJsonObject {
                    put("name", variable.name())
                    put("type", variable.typeName())
                    put("value", rendered)
                })
                emittedCount += 1
            }
        }
    }

    private fun renderValue(value: Value?): String {
        if (value == null) {
            return "null"
        }

        return when (value) {
            is StringReference -> value.value().take(200)
            else -> value.toString().take(200)
        }
    }

    private fun classPatternMatches(className: String, classPattern: String): Boolean {
        if (!classPattern.contains('*')) {
            return className == classPattern
        }

        val regex = classPattern
            .replace(".", "\\.")
            .replace("*", ".*")
            .toRegex()
        return regex.matches(className)
    }

    private fun formatLocation(location: Location): String {
        return "${location.declaringType().name()}:${location.lineNumber()}"
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
            ThreadReference.THREAD_STATUS_ZOMBIE,
            -> "WAITING"
            else -> "WAITING"
        }
    }

    private fun isDaemonThread(thread: ThreadReference): Boolean {
        return try {
            val daemonField = thread.referenceType()
                .allFields()
                .firstOrNull { it.name() == "daemon" }
                ?: return false
            val value = thread.getValue(daemonField)
            (value as? BooleanValue)?.value() ?: false
        } catch (_: Exception) {
            false
        }
    }

    private fun findSocketAttachConnector(): AttachingConnector {
        val vmm = Bootstrap.virtualMachineManager()
        return vmm.attachingConnectors().firstOrNull {
            it.name() == "com.sun.jdi.SocketAttach"
        } ?: throw RpcException(INTERNAL_ERROR, "SocketAttach connector not found in JDK")
    }

    private fun normalizeDisconnectReason(reason: String): String {
        val lowered = reason.lowercase()
        return when {
            lowered.contains("transport") || lowered.contains("device offline") ||
                lowered.contains("connection reset") -> "device_disconnected"

            lowered.contains("killed") || lowered.contains("terminated") ||
                lowered.contains("force stop") -> "app_killed"

            else -> "app_crashed"
        }
    }
}
