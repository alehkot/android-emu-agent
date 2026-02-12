package dev.androidemu.jdibridge

import com.sun.jdi.AbsentInformationException
import com.sun.jdi.BooleanValue
import com.sun.jdi.Bootstrap
import com.sun.jdi.ClassType
import com.sun.jdi.Location
import com.sun.jdi.ThreadReference
import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.VirtualMachine
import com.sun.jdi.connect.AttachingConnector
import com.sun.jdi.event.BreakpointEvent
import com.sun.jdi.event.ClassPrepareEvent
import com.sun.jdi.event.StepEvent
import com.sun.jdi.event.VMDeathEvent
import com.sun.jdi.event.VMDisconnectEvent
import com.sun.jdi.request.BreakpointRequest
import com.sun.jdi.request.ClassPrepareRequest
import com.sun.jdi.request.EventRequest
import com.sun.jdi.request.StepRequest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.util.Locale
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * Manages a single JDI connection to a target JVM.
 *
 * Thread safety: [status] and command handlers may run on the main RPC thread while
 * the event loop consumes JDI events on a background daemon thread.
 */
class JdiSession(
    private val notificationEmitter: (JsonElement) -> Unit,
) {
    companion object {
        const val DEFAULT_STEP_TIMEOUT_SECONDS = 10.0
        const val ANR_WARNING_SECONDS = 8.0
    }

    private data class BreakpointState(
        val id: Int,
        val classPattern: String,
        val line: Int,
        var status: String,
        var location: String? = null,
        var request: BreakpointRequest? = null,
        var prepareRequest: ClassPrepareRequest? = null,
    )

    private data class PendingStep(
        val action: String,
        val threadName: String,
        val request: StepRequest,
        val completion: CompletableFuture<JsonObject>,
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
    private var activeStep: PendingStep? = null
    private val inspector = Inspector()
    private val suspendedAtMs = mutableMapOf<Long, Long>()

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
            activeStep = null
            suspendedAtMs.clear()
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
        synchronized(stateLock) {
            activeStep = null
            suspendedAtMs.clear()
        }

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

        return buildJsonObject {
            put("status", "resumed")
            put("scope", "thread")
            put("thread", thread.name())
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
                throw RpcException(INTERNAL_ERROR, "Failed to suspend thread: ${e.message ?: "unknown"}")
            }
        }
        markThreadSuspended(thread)

        clearExistingStepRequests(machine, thread)

        val request = machine.eventRequestManager().createStepRequest(
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
        synchronized(stateLock) {
            activeStep = PendingStep(
                action = action,
                threadName = thread.name(),
                request = request,
                completion = completion,
            )
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
            throw RpcException(INTERNAL_ERROR, "Failed to resume thread for step: ${e.message ?: "unknown"}")
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
            throw RpcException(INVALID_REQUEST, "VM is disconnected: ${disconnectReason ?: "unknown"}")
        }
        return vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")
    }

    private fun resolveThread(machine: VirtualMachine, threadName: String): ThreadReference {
        val threads = try {
            machine.allThreads()
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to list threads: ${e.message ?: "unknown"}")
        }
        return threads.firstOrNull { it.name() == threadName }
            ?: throw RpcException(INVALID_REQUEST, "Thread not found: $threadName")
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
                    var shouldResumeSet = true
                    try {
                        for (event in eventSet) {
                            when (event) {
                                is BreakpointEvent -> {
                                    if (!handleBreakpointEvent(event)) {
                                        shouldResumeSet = false
                                    }
                                }
                                is ClassPrepareEvent -> handleClassPrepareEvent(machine, event)
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
        val pending = synchronized(stateLock) {
            val current = activeStep
            activeStep = null
            suspendedAtMs.clear()
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

    private fun handleBreakpointEvent(event: BreakpointEvent): Boolean {
        val request = event.request() as? BreakpointRequest
        val requestId = request?.getProperty("breakpoint_id") as? Int
        val locationText = formatLocation(event.location())
        val stopped = buildStoppedPayload(event.thread(), event.location())
        markThreadSuspended(event.thread())

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
                for ((key, value) in stopped) {
                    put(key, value)
                }
            },
        )

        // Keep thread suspended at breakpoint for step/inspect flows.
        return false
    }

    private fun handleStepEvent(machine: VirtualMachine, event: StepEvent): Boolean {
        val stepRequest = event.request() as? StepRequest ?: return true

        val pending = synchronized(stateLock) {
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

    private fun buildStoppedPayload(thread: ThreadReference, fallbackLocation: Location): JsonObject {
        val frames = try {
            thread.frames()
        } catch (_: Exception) {
            emptyList()
        }
        val frameLocations = frames.map { it.location() }
        val selection = if (frameLocations.isEmpty()) {
            FrameFilter.Selection(selectedIndex = 0, filteredCount = 0)
        } else {
            FrameFilter.selectPrimaryFrame(frameLocations)
        }
        val selectedIndex = selection.selectedIndex.coerceIn(0, (frames.size - 1).coerceAtLeast(0))
        val selectedLocation = frames.getOrNull(selectedIndex)?.location() ?: fallbackLocation
        val inspectedFrame = try {
            inspector.inspectFrame(
                thread = thread,
                frameIndex = selectedIndex,
                tokenBudget = TokenBudget.DEFAULT_MAX_TOKENS,
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
            put("method", selectedLocation.method().name())
            put("thread", thread.name())
            put("locals", locals)
            put("token_usage_estimate", tokenUsage)
            put("truncated", truncated)
            if (selection.filteredCount > 0) {
                put("frame_filters", buildJsonArray {
                    add(buildJsonObject {
                        put("filtered", true)
                        put("count", selection.filteredCount)
                        put("reason", "coroutine_internal")
                    })
                })
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
        val since = synchronized(stateLock) {
            suspendedAtMs[thread.uniqueID()]
        } ?: return null
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
            suspendedAtMs.putIfAbsent(thread.uniqueID(), System.currentTimeMillis())
        }
    }

    private fun markThreadResumed(thread: ThreadReference) {
        synchronized(stateLock) {
            suspendedAtMs.remove(thread.uniqueID())
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
        val existing = try {
            manager.stepRequests().filter { it.thread() == thread }
        } catch (_: Exception) {
            emptyList()
        }
        for (request in existing) {
            clearStepRequest(machine, request)
        }
    }

    private fun emitEvent(type: String, extraParams: JsonElement) {
        val paramsObject = extraParams as? JsonObject
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
            activeStep = null
            suspendedAtMs.clear()
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
