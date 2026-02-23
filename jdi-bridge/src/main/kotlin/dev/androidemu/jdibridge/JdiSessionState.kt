package dev.androidemu.jdibridge

import com.sun.jdi.ObjectReference
import com.sun.jdi.VirtualMachine
import com.sun.jdi.request.BreakpointRequest
import com.sun.jdi.request.ClassPrepareRequest
import com.sun.jdi.request.ExceptionRequest
import com.sun.jdi.request.StepRequest
import java.util.concurrent.CompletableFuture
import kotlinx.serialization.json.JsonObject

internal data class BreakpointState(
    val id: Int,
    val classPattern: String,
    val line: Int,
    var status: String,
    var location: String? = null,
    var request: BreakpointRequest? = null,
    var prepareRequest: ClassPrepareRequest? = null,
    val condition: String? = null,
    val compiledCondition: ConditionExpression? = null,
    val logMessage: String? = null,
    val captureStack: Boolean = false,
    val stackMaxFrames: Int = JdiSession.DEFAULT_LOGPOINT_STACK_FRAMES,
    var hitCount: Long = 0,
)

internal data class ExceptionBreakpointState(
    val id: Int,
    val classPattern: String,
    val caught: Boolean,
    val uncaught: Boolean,
    var status: String,
    var request: ExceptionRequest? = null,
    var prepareRequest: ClassPrepareRequest? = null,
)

internal data class PendingStep(
    val action: String,
    val threadName: String,
    val request: StepRequest,
    val completion: CompletableFuture<JsonObject>,
)

internal class JdiSessionState {
    @Volatile var vm: VirtualMachine? = null
    @Volatile var eventThread: Thread? = null
    @Volatile var disconnected = false
    @Volatile var disconnectReason: String? = null
    @Volatile var mapping: ProguardMapping? = null

    val lock = Any()
    val breakpoints = linkedMapOf<Int, BreakpointState>()
    val exceptionBreakpoints = linkedMapOf<Int, ExceptionBreakpointState>()
    var nextBreakpointId = 1
    var activeStep: PendingStep? = null
    val suspendedAtMs = mutableMapOf<Long, Long>()
    val objectIdsByUniqueId = mutableMapOf<Long, String>()
    val objectRefsById = mutableMapOf<String, ObjectReference>()
    var nextObjectId = 1
}
