package dev.androidemu.jdibridge

import com.sun.jdi.AbsentInformationException
import com.sun.jdi.ArrayReference
import com.sun.jdi.CharValue
import com.sun.jdi.IntegerValue
import com.sun.jdi.ObjectReference
import com.sun.jdi.PrimitiveValue
import com.sun.jdi.StackFrame
import com.sun.jdi.StringReference
import com.sun.jdi.ThreadReference
import com.sun.jdi.Value
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Serializes frame locals with bounded depth and token budget controls.
 */
class Inspector(
    private val maxStringLength: Int = 200,
    private val maxCollectionItems: Int = 10,
    private val maxObjectFields: Int = 10,
) {
    fun inspectFrame(
        thread: ThreadReference,
        frameIndex: Int = 0,
        tokenBudget: Int = TokenBudget.DEFAULT_MAX_TOKENS,
    ): JsonObject {
        if (frameIndex < 0) {
            throw RpcException(INVALID_PARAMS, "frame_index must be >= 0")
        }

        if (!thread.isSuspended) {
            return buildJsonObject {
                put("locals", buildJsonArray { })
                put("token_usage_estimate", 0)
                put("truncated", false)
            }
        }

        val frameCount = try {
            thread.frameCount()
        } catch (_: Exception) {
            0
        }
        if (frameIndex >= frameCount) {
            throw RpcException(INVALID_PARAMS, "frame_index out of range: $frameIndex")
        }

        val frame = try {
            thread.frame(frameIndex)
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to inspect frame: ${e.message ?: "unknown"}")
        }

        val budget = TokenBudget(tokenBudget)
        val locals = serializeLocals(frame, budget)
        return buildJsonObject {
            put("locals", locals)
            put("token_usage_estimate", budget.tokenUsageEstimate())
            put("truncated", budget.truncated)
        }
    }

    private fun serializeLocals(frame: StackFrame, budget: TokenBudget): JsonElement {
        val variables = try {
            frame.visibleVariables()
        } catch (_: AbsentInformationException) {
            return buildJsonArray { }
        } catch (_: Exception) {
            return buildJsonArray { }
        }

        return buildJsonArray {
            for (variable in variables) {
                val overhead = variable.name().length + variable.typeName().length + 24
                if (!budget.tryConsume(overhead)) {
                    budget.markTruncated()
                    break
                }

                val value = try {
                    frame.getValue(variable)
                } catch (_: Exception) {
                    null
                }

                add(buildJsonObject {
                    put("name", variable.name())
                    put("type", variable.typeName())
                    put("value", serializeValue(value, budget, depth = 1))
                })
            }
        }
    }

    private fun serializeValue(value: Value?, budget: TokenBudget, depth: Int): JsonElement {
        if (value == null) {
            budget.tryConsume(4)
            return JsonNull
        }

        return when (value) {
            is PrimitiveValue -> serializePrimitive(value, budget)
            is StringReference -> serializeString(value, budget)
            is ArrayReference -> serializeArray(value, budget, depth)
            is ObjectReference -> serializeObject(value, budget, depth)
            else -> serializeFallback(value.toString(), budget)
        }
    }

    private fun serializePrimitive(value: PrimitiveValue, budget: TokenBudget): JsonElement {
        val primitive: JsonElement = when (value) {
            is CharValue -> JsonPrimitive(value.value().toString())
            else -> JsonPrimitive(value.toString())
        }
        budget.tryConsume(primitive.toString().length)
        return primitive
    }

    private fun serializeString(value: StringReference, budget: TokenBudget): JsonElement {
        val text = value.value().take(maxStringLength)
        budget.tryConsume(text.length + 2)
        return JsonPrimitive(text)
    }

    private fun serializeArray(value: ArrayReference, budget: TokenBudget, depth: Int): JsonElement {
        if (depth <= 0) {
            budget.tryConsume(20)
            return buildJsonObject {
                put("length", value.length())
            }
        }

        val values: List<Value?> = try {
            value.values
        } catch (_: Exception) {
            emptyList()
        }
        val shown = values.take(maxCollectionItems)
        if (values.size > shown.size) {
            budget.markTruncated()
        }

        return buildJsonObject {
            put("length", values.size)
            put("items", buildJsonArray {
                for (item in shown) {
                    add(serializeValue(item, budget, depth - 1))
                }
            })
        }
    }

    private fun serializeObject(value: ObjectReference, budget: TokenBudget, depth: Int): JsonElement {
        val className = value.referenceType().name()
        if (!budget.tryConsume(className.length + 12)) {
            return buildJsonObject {
                put("class", className)
            }
        }

        if (isListLike(className)) {
            val listLike = serializeListLike(value, budget, depth)
            if (listLike != null) {
                return listLike
            }
        }

        if (depth <= 0) {
            return buildJsonObject {
                put("class", className)
            }
        }

        val fields = value.referenceType().allFields().filter { !it.isStatic }
        val shownFields = fields.take(maxObjectFields)
        if (fields.size > shownFields.size) {
            budget.markTruncated()
        }

        return buildJsonObject {
            put("class", className)
            put("fields", buildJsonObject {
                for (field in shownFields) {
                    if (!budget.tryConsume(field.name().length + 8)) {
                        budget.markTruncated()
                        break
                    }
                    val fieldValue = try {
                        value.getValue(field)
                    } catch (_: Exception) {
                        null
                    }
                    put(field.name(), serializeValue(fieldValue, budget, depth - 1))
                }
            })
        }
    }

    private fun serializeListLike(
        value: ObjectReference,
        budget: TokenBudget,
        depth: Int,
    ): JsonElement? {
        val fields = value.referenceType().allFields()
        val sizeField = fields.firstOrNull { it.name() == "size" } ?: return null
        val rawSize = try {
            value.getValue(sizeField)
        } catch (_: Exception) {
            null
        }
        val length = (rawSize as? IntegerValue)?.value() ?: -1

        val dataField = fields.firstOrNull { it.name() == "elementData" } ?: return null
        val rawData = try {
            value.getValue(dataField)
        } catch (_: Exception) {
            null
        }
        val backingArray = rawData as? ArrayReference ?: return null

        val maxItems = if (length >= 0) minOf(length, maxCollectionItems) else maxCollectionItems
        val allValues: List<Value?> = try {
            backingArray.values
        } catch (_: Exception) {
            emptyList()
        }
        val shown = allValues.take(maxItems)
        if (length > shown.size) {
            budget.markTruncated()
        }

        return buildJsonObject {
            put("length", if (length >= 0) length else allValues.size)
            put("items", buildJsonArray {
                for (item in shown) {
                    add(serializeValue(item, budget, depth - 1))
                }
            })
        }
    }

    private fun serializeFallback(text: String, budget: TokenBudget): JsonElement {
        val value = text.take(maxStringLength)
        budget.tryConsume(value.length + 2)
        return JsonPrimitive(value)
    }

    private fun isListLike(className: String): Boolean {
        return className.startsWith("java.util.") && className.contains("List")
    }
}
