package dev.androidemu.jdibridge

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * JSON-RPC 2.0 request/response handling.
 *
 * Protocol: one JSON object per line on stdin/stdout.
 * Notifications (no id) flow bridge → python for async events.
 */

val json = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
}

data class RpcRequest(
    val id: Int?,
    val method: String,
    val params: JsonObject,
)

@Serializable
data class RpcError(
    val code: Int,
    val message: String,
    val data: JsonElement? = null,
)

@Serializable
data class RpcResponse(
    val jsonrpc: String = "2.0",
    val id: Int? = null,
    val result: JsonElement? = null,
    val error: RpcError? = null,
)

// Standard JSON-RPC error codes
const val PARSE_ERROR = -32700
const val INVALID_REQUEST = -32600
const val METHOD_NOT_FOUND = -32601
const val INVALID_PARAMS = -32602
const val INTERNAL_ERROR = -32603

fun parseRequest(line: String): RpcRequest {
    val obj = json.parseToJsonElement(line).jsonObject

    val jsonrpc = obj["jsonrpc"]?.jsonPrimitive?.content
    if (jsonrpc != "2.0") {
        throw RpcException(INVALID_REQUEST, "Missing or invalid jsonrpc version")
    }

    val method = obj["method"]?.jsonPrimitive?.content
        ?: throw RpcException(INVALID_REQUEST, "Missing method")

    val id = obj["id"]?.jsonPrimitive?.intOrNull

    val params = when (val p = obj["params"]) {
        is JsonObject -> p
        null -> JsonObject(emptyMap())
        else -> throw RpcException(INVALID_PARAMS, "params must be an object")
    }

    return RpcRequest(id = id, method = method, params = params)
}

fun successResponse(id: Int?, result: JsonElement): String {
    val resp = RpcResponse(id = id, result = result)
    return json.encodeToString(resp)
}

fun errorResponse(id: Int?, code: Int, message: String, data: JsonElement? = null): String {
    val resp = RpcResponse(id = id, error = RpcError(code = code, message = message, data = data))
    return json.encodeToString(resp)
}

class RpcException(val code: Int, override val message: String) : Exception(message)
