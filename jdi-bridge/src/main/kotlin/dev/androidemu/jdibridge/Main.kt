package dev.androidemu.jdibridge

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.BufferedReader
import java.io.InputStreamReader

/**
 * JDI Bridge entry point.
 *
 * Reads JSON-RPC 2.0 requests from stdin (one per line),
 * dispatches to handlers, writes responses to stdout.
 * Logs go to stderr to keep the JSON-RPC channel clean.
 */

private val outputLock = Any()

internal fun sendLine(line: String) {
    synchronized(outputLock) {
        println(line)
        System.out.flush()
    }
}

fun main() {
    log("jdi-bridge starting")

    // Initialize Commands with a notification emitter that writes to stdout
    Commands.init { notification: JsonElement ->
        sendLine(json.encodeToString(notification))
    }

    val reader = BufferedReader(InputStreamReader(System.`in`))

    while (true) {
        val line = reader.readLine() ?: break // EOF = parent died

        if (line.isBlank()) continue

        val response = handleLine(line)
        if (response != null) {
            sendLine(response)
        }
    }

    log("jdi-bridge exiting (stdin closed)")
}

internal fun handleLine(line: String): String? {
    val request = try {
        parseRequest(line)
    } catch (e: RpcException) {
        return errorResponse(null, e.code, e.message)
    } catch (e: Exception) {
        return errorResponse(null, PARSE_ERROR, "Failed to parse JSON: ${e.message}")
    }

    return try {
        dispatch(request)
    } catch (e: RpcException) {
        errorResponse(request.id, e.code, e.message)
    } catch (e: Exception) {
        errorResponse(request.id, INTERNAL_ERROR, "Internal error: ${e.message}")
    }
}

private fun dispatch(request: RpcRequest): String? {
    // Try Commands first (attach/detach/status)
    val cmdResult = Commands.dispatch(request)
    if (cmdResult != null) return cmdResult

    // Built-in methods
    return when (request.method) {
        "ping" -> {
            val result = buildJsonObject { put("pong", true) }
            successResponse(request.id, result)
        }

        "shutdown" -> {
            log("shutdown requested")
            val result = buildJsonObject { put("status", "shutting_down") }
            val response = successResponse(request.id, result)
            // Print the response before exiting
            sendLine(response)
            System.exit(0)
            null // unreachable
        }

        else -> {
            errorResponse(request.id, METHOD_NOT_FOUND, "Unknown method: ${request.method}")
        }
    }
}

internal fun log(message: String) {
    System.err.println("[jdi-bridge] $message")
    System.err.flush()
}
