package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * Routes JSON-RPC methods to the single [JdiSession].
 *
 * Initialized with a notification callback that writes to stdout
 * (synchronized via the output lock in Main.kt).
 */
object Commands {
    private var session: JdiSession? = null

    fun init(notificationEmitter: (JsonElement) -> Unit) {
        session = JdiSession(notificationEmitter)
    }

    /**
     * Dispatch a request to the appropriate handler.
     * Returns null if the method is not handled by Commands (fall through to Main).
     */
    fun dispatch(request: RpcRequest): String? {
        val s = session ?: return null

        return when (request.method) {
            "attach" -> {
                val host = request.params["host"]?.jsonPrimitive?.content ?: "localhost"
                val port = request.params["port"]?.jsonPrimitive?.int
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: port")
                val result = s.attach(host, port)
                successResponse(request.id, result)
            }

            "detach" -> {
                val result = s.detach()
                successResponse(request.id, result)
            }

            "status" -> {
                val result = s.status()
                successResponse(request.id, result)
            }

            "set_breakpoint" -> {
                val classPattern = request.params["class_pattern"]?.jsonPrimitive?.content
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: class_pattern")
                val line = request.params["line"]?.jsonPrimitive?.int
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: line")
                val result = s.setBreakpoint(classPattern, line)
                successResponse(request.id, result)
            }

            "remove_breakpoint" -> {
                val breakpointId = request.params["breakpoint_id"]?.jsonPrimitive?.int
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: breakpoint_id")
                val result = s.removeBreakpoint(breakpointId)
                successResponse(request.id, result)
            }

            "list_breakpoints" -> {
                val result = s.listBreakpoints()
                successResponse(request.id, result)
            }

            "list_threads" -> {
                val includeDaemon = request.params["include_daemon"]
                    ?.jsonPrimitive
                    ?.booleanOrNull
                    ?: false
                val maxThreads = request.params["max_threads"]
                    ?.jsonPrimitive
                    ?.intOrNull
                    ?: 20
                val result = s.listThreads(includeDaemon, maxThreads)
                successResponse(request.id, result)
            }

            "step_over" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val timeoutSeconds = request.params["timeout_seconds"]
                    ?.jsonPrimitive
                    ?.doubleOrNull
                    ?: JdiSession.DEFAULT_STEP_TIMEOUT_SECONDS
                val result = s.stepOver(threadName, timeoutSeconds)
                successResponse(request.id, result)
            }

            "step_into" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val timeoutSeconds = request.params["timeout_seconds"]
                    ?.jsonPrimitive
                    ?.doubleOrNull
                    ?: JdiSession.DEFAULT_STEP_TIMEOUT_SECONDS
                val result = s.stepInto(threadName, timeoutSeconds)
                successResponse(request.id, result)
            }

            "step_out" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val timeoutSeconds = request.params["timeout_seconds"]
                    ?.jsonPrimitive
                    ?.doubleOrNull
                    ?: JdiSession.DEFAULT_STEP_TIMEOUT_SECONDS
                val result = s.stepOut(threadName, timeoutSeconds)
                successResponse(request.id, result)
            }

            "resume" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content
                val result = s.resume(threadName)
                successResponse(request.id, result)
            }

            "stack_trace" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val maxFrames = request.params["max_frames"]?.jsonPrimitive?.intOrNull ?: 10
                val result = s.stackTrace(threadName, maxFrames)
                successResponse(request.id, result)
            }

            "inspect_variable" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val frameIndex = request.params["frame_index"]?.jsonPrimitive?.intOrNull ?: 0
                val variablePath = request.params["variable_path"]?.jsonPrimitive?.content
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: variable_path")
                val depth = request.params["depth"]?.jsonPrimitive?.intOrNull ?: 1
                val result = s.inspectVariable(
                    threadName = threadName,
                    frameIndex = frameIndex,
                    variablePath = variablePath,
                    depth = depth,
                )
                successResponse(request.id, result)
            }

            "evaluate" -> {
                val threadName = request.params["thread_name"]?.jsonPrimitive?.content ?: "main"
                val frameIndex = request.params["frame_index"]?.jsonPrimitive?.intOrNull ?: 0
                val expression = request.params["expression"]?.jsonPrimitive?.content
                    ?: throw RpcException(INVALID_PARAMS, "Missing required param: expression")
                val result = s.evaluate(
                    threadName = threadName,
                    frameIndex = frameIndex,
                    expression = expression,
                )
                successResponse(request.id, result)
            }

            else -> null
        }
    }
}
