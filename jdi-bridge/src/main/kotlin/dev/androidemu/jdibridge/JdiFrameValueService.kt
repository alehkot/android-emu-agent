package dev.androidemu.jdibridge

import com.sun.jdi.AbsentInformationException
import com.sun.jdi.IncompatibleThreadStateException
import com.sun.jdi.Location
import com.sun.jdi.ObjectCollectedException
import com.sun.jdi.ObjectReference
import com.sun.jdi.PrimitiveValue
import com.sun.jdi.StackFrame
import com.sun.jdi.StringReference
import com.sun.jdi.ThreadReference
import com.sun.jdi.Value
import java.util.Locale
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

internal class JdiFrameValueService(
    private val state: JdiSessionState,
    private val inspector: Inspector,
) {
    companion object {
        private const val ERR_NOT_SUSPENDED = "ERR_NOT_SUSPENDED"
        private const val ERR_OBJECT_COLLECTED = "ERR_OBJECT_COLLECTED"
        private const val ERR_EVAL_UNSUPPORTED = "ERR_EVAL_UNSUPPORTED"
    }

    fun stackTrace(thread: ThreadReference, maxFrames: Int): JsonElement {
        if (maxFrames <= 0) {
            throw RpcException(INVALID_PARAMS, "max_frames must be > 0")
        }

        val frames = requireThreadFrames(thread)
        val activeMapping = state.mapping

        val entries = mutableListOf<JsonObject>()
        var index = 0
        while (index < frames.size && entries.size < maxFrames) {
            val frame = frames[index]
            val location = frame.location()
            if (FrameFilter.isCoroutineInternal(location)) {
                var filteredCount = 0
                while (index < frames.size && FrameFilter.isCoroutineInternal(frames[index].location())) {
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
                    val methodArity = runCatching { method.argumentTypeNames().size }.getOrNull()
                    put("index", index)
                    put("class", activeMapping?.deobfuscateClass(rawClassName) ?: rawClassName)
                    put(
                        "method",
                        activeMapping?.deobfuscateMethod(rawClassName, method.name(), methodArity)
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
        thread: ThreadReference,
        frameIndex: Int,
        variablePath: String,
        depth: Int,
    ): JsonElement {
        if (frameIndex < 0) {
            throw RpcException(INVALID_PARAMS, "frame_index must be >= 0")
        }
        if (depth <= 0 || depth > 3) {
            throw RpcException(INVALID_PARAMS, "depth must be in range 1..3")
        }
        if (variablePath.isBlank()) {
            throw RpcException(INVALID_PARAMS, "variable_path must not be blank")
        }

        val frame = resolveFrame(thread, frameIndex)
        val value = resolveValuePath(frame, variablePath)
        val activeMapping = state.mapping
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
            put("token_usage_estimate", inspected["token_usage_estimate"] ?: JsonPrimitive(0))
            put("truncated", inspected["truncated"] ?: JsonPrimitive(false))
        }
    }

    fun evaluate(
        thread: ThreadReference,
        frameIndex: Int,
        expression: String,
    ): JsonElement {
        if (frameIndex < 0) {
            throw RpcException(INVALID_PARAMS, "frame_index must be >= 0")
        }
        val trimmedExpression = expression.trim()
        if (trimmedExpression.isEmpty()) {
            throw RpcException(INVALID_PARAMS, "expression must not be blank")
        }

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
                val activeMapping = state.mapping
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
            put("token_usage_estimate", result["token_usage_estimate"] ?: JsonPrimitive(0))
            put("truncated", result["truncated"] ?: JsonPrimitive(false))
        }
    }

    fun buildStoppedPayload(thread: ThreadReference, fallbackLocation: Location): JsonObject {
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
        val activeMapping = state.mapping
        val rawClassName = selectedLocation.declaringType().name()
        val selectedMethod = selectedLocation.method()
        val selectedMethodArity = runCatching { selectedMethod.argumentTypeNames().size }.getOrNull()
        val mappedMethod =
            activeMapping?.deobfuscateMethod(rawClassName, selectedMethod.name(), selectedMethodArity)
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
                            },
                        )
                    },
                )
            }
            if (warning != null) {
                put("warning", warning)
            }
        }
    }

    fun buildLogpointStack(thread: ThreadReference, maxFrames: Int): JsonObject {
        val frames =
            try {
                thread.frames()
            } catch (_: Exception) {
                emptyList()
            }
        val activeMapping = state.mapping
        val shown = minOf(maxFrames, frames.size)
        val frameEntries =
            buildJsonArray {
                for (index in 0 until shown) {
                    val frame = frames[index]
                    val location = frame.location()
                    val rawClassName = location.declaringType().name()
                    val method = location.method()
                    val methodArity = runCatching { method.argumentTypeNames().size }.getOrNull()
                    add(
                        buildJsonObject {
                            put("index", index)
                            put("class", activeMapping?.deobfuscateClass(rawClassName) ?: rawClassName)
                            put(
                                "method",
                                activeMapping?.deobfuscateMethod(
                                    rawClassName,
                                    method.name(),
                                    methodArity,
                                ) ?: method.name(),
                            )
                            put("line", location.lineNumber())
                            val source = runCatching { location.sourceName() }.getOrNull()
                            if (source != null) {
                                put("source", source)
                            }
                        },
                    )
                }
            }

        return buildJsonObject {
            put("frame_count", frames.size)
            put("shown_frames", shown)
            put("max_frames", maxFrames)
            put("truncated", frames.size > shown)
            put("frames", frameEntries)
        }
    }

    fun evaluateLogMessage(thread: ThreadReference, template: String, hitCount: Long): String {
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

    fun resolveValuePath(frame: StackFrame, variablePath: String): Value? {
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

    fun invalidateObjectCache() {
        synchronized(state.lock) { invalidateObjectCacheLocked() }
    }

    fun invalidateObjectCacheLocked() {
        state.objectIdsByUniqueId.clear()
        state.objectRefsById.clear()
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
        } catch (_: IncompatibleThreadStateException) {
            throw RpcException(
                INVALID_REQUEST,
                "$ERR_NOT_SUSPENDED: thread '${thread.name()}' is not suspended",
            )
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to read thread frames: ${e.message ?: "unknown"}")
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
                throw RpcException(INTERNAL_ERROR, "Failed to read frame locals: ${e.message ?: "unknown"}")
            } ?: throw RpcException(INVALID_REQUEST, "Local variable not found: $root")

        return try {
            frame.getValue(local)
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to read local '$root': ${e.message ?: "unknown"}")
        }
    }

    private fun resolveFieldValue(objectRef: ObjectReference, fieldName: String): Value? {
        val referenceType = objectRef.referenceType()
        val rawClassName = referenceType.name()
        val fields = referenceType.allFields()
        val field =
            fields.firstOrNull { it.name() == fieldName }
                ?: run {
                    val remapped = state.mapping?.obfuscateField(rawClassName, fieldName)
                    if (remapped != null) {
                        fields.firstOrNull { it.name() == remapped }
                    } else {
                        null
                    }
                }
                ?: throw RpcException(
                    INVALID_REQUEST,
                    "Field '$fieldName' not found on ${state.mapping?.deobfuscateClass(rawClassName) ?: rawClassName}",
                )
        return try {
            objectRef.getValue(field)
        } catch (_: ObjectCollectedException) {
            throw RpcException(
                INVALID_REQUEST,
                "$ERR_OBJECT_COLLECTED: object was collected while reading '$fieldName'",
            )
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to read field '$fieldName': ${e.message ?: "unknown"}")
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
            } ?: return objectRef.toString()

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
        } catch (_: ObjectCollectedException) {
            throw RpcException(INVALID_REQUEST, "$ERR_OBJECT_COLLECTED: object no longer available")
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to invoke toString(): ${e.message ?: "unknown"}")
        }
    }

    private fun cacheObjectId(objectRef: ObjectReference): String {
        val uniqueId = objectRef.uniqueID()
        synchronized(state.lock) {
            val existing = state.objectIdsByUniqueId[uniqueId]
            if (existing != null) {
                state.objectRefsById[existing] = objectRef
                return existing
            }

            val id = "obj_${state.nextObjectId++}"
            state.objectIdsByUniqueId[uniqueId] = id
            state.objectRefsById[id] = objectRef
            return id
        }
    }

    private fun resolveCachedObject(objectId: String): ObjectReference {
        synchronized(state.lock) {
            return state.objectRefsById[objectId]
                ?: throw RpcException(
                    INVALID_REQUEST,
                    "$ERR_OBJECT_COLLECTED: stale object id '$objectId'",
                )
        }
    }

    private fun estimateTokenUsage(charCount: Int): Int {
        if (charCount <= 0) {
            return 0
        }
        return (charCount + 3) / 4
    }

    private fun formatLocation(location: Location): String {
        val rawClassName = location.declaringType().name()
        val className = state.mapping?.deobfuscateClass(rawClassName) ?: rawClassName
        return "$className:${location.lineNumber()}"
    }

    private fun anrWarningForThread(thread: ThreadReference): String? {
        if (thread.name() != "main") {
            return null
        }
        val since = synchronized(state.lock) { state.suspendedAtMs[thread.uniqueID()] } ?: return null
        val elapsedSeconds = (System.currentTimeMillis() - since) / 1000.0
        if (elapsedSeconds < JdiSession.ANR_WARNING_SECONDS) {
            return null
        }
        return String.format(
            Locale.US,
            "main thread suspended for %.1fs — Android may trigger ANR. Consider resuming soon.",
            elapsedSeconds,
        )
    }
}
