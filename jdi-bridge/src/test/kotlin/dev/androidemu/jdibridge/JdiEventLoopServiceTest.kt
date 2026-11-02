package dev.androidemu.jdibridge

import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.VirtualMachine
import com.sun.jdi.ThreadReference
import com.sun.jdi.Location
import com.sun.jdi.ReferenceType
import com.sun.jdi.event.StepEvent
import com.sun.jdi.request.EventRequestManager
import com.sun.jdi.request.StepRequest
import java.lang.reflect.Proxy
import java.util.concurrent.CompletableFuture
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Unit-level tests for disconnect bookkeeping, without a live target VM. */
class JdiEventLoopServiceTest {

    private class Harness {
        val events = mutableListOf<Pair<String, JsonObject>>()
        val state = JdiSessionState()
        val service: JdiEventLoopService
        val threadControlService: JdiThreadControlService

        init {
            val inspector = Inspector()
            val frameValueService = JdiFrameValueService(state, inspector)
            threadControlService = JdiThreadControlService(state, frameValueService)
            val emit: (String, JsonObject) -> Unit = { name, params ->
                synchronized(events) { events.add(name to params) }
            }
            val breakpointService =
                JdiBreakpointService(state, threadControlService, frameValueService, emit)
            service =
                JdiEventLoopService(
                    state,
                    breakpointService,
                    threadControlService,
                    frameValueService,
                    emit,
                )
        }

        fun disconnectEvents() = events.filter { it.first == "vm_disconnected" }
    }

    @Test
    fun `repeated disconnects emit a single notification`() {
        val harness = Harness()

        // A single EventSet can carry VMDeathEvent alongside another event whose handling
        // then throws VMDisconnectedException, so handleDisconnect runs twice per loop pass.
        harness.service.handleDisconnect("VM death")
        harness.service.handleDisconnect("VM disconnected")

        assertEquals(
            1,
            harness.disconnectEvents().size,
            "Disconnect must be reported once, not once per triggering event",
        )
    }

    @Test
    fun `first disconnect reason is the one reported`() {
        val harness = Harness()

        harness.service.handleDisconnect("process was killed")
        harness.service.handleDisconnect("Event loop error: transport closed")

        val params = harness.disconnectEvents().single().second
        assertEquals("app_killed", params["reason"]?.jsonPrimitive?.content)
        assertEquals("process was killed", params["detail"]?.jsonPrimitive?.content)
        assertEquals("app_killed", harness.state.disconnectReason)
    }

    @Test
    fun `concurrent disconnects emit a single notification`() {
        val harness = Harness()
        val threads = 8
        val pool = Executors.newFixedThreadPool(threads)
        val start = CountDownLatch(1)

        try {
            repeat(threads) {
                pool.submit {
                    start.await(5, TimeUnit.SECONDS)
                    harness.service.handleDisconnect("VM disconnected")
                }
            }
            start.countDown()
            pool.shutdown()
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS), "workers should finish")
        } finally {
            pool.shutdownNow()
        }

        assertEquals(1, harness.disconnectEvents().size)
    }

    @Test
    fun `disconnect still marks the session disconnected`() {
        val harness = Harness()
        assertFalse(harness.state.disconnected)

        harness.service.handleDisconnect("VM disconnected")

        assertTrue(harness.state.disconnected)
    }

    @Test
    fun `guard resets so a re-attached session can report a new disconnect`() {
        val harness = Harness()
        harness.service.handleDisconnect("VM disconnected")
        assertEquals(1, harness.disconnectEvents().size)

        // What JdiSession.attach does when the session is reused.
        harness.state.disconnected = false
        harness.state.disconnectHandled.set(false)
        harness.state.disconnectReason = null

        harness.service.handleDisconnect("process was killed")

        assertEquals(2, harness.disconnectEvents().size)
        assertEquals("app_killed", harness.state.disconnectReason)
    }

    @Test
    fun `disconnect during stopped payload construction completes the pending step`() {
        for (failurePoint in listOf("event", "location", "suspension")) {
            val harness = Harness()
            val request = proxy<StepRequest> { _, _ -> null }
            val manager = proxy<EventRequestManager> { _, _ -> null }
            val machine = proxy<VirtualMachine> { _, _ -> manager }
            val completion = CompletableFuture<JsonObject>()
            harness.state.activeStep = PendingStep("step_over", "main", request, completion)
            val event = stepEvent(request, failurePoint = failurePoint)


            try {
                harness.threadControlService.handleStepEvent(machine, event)
                throw AssertionError("Expected injected disconnect at $failurePoint")
            } catch (_: VMDisconnectedException) {
                // Match the production event loop's disconnect path.
                harness.service.handleDisconnect("VM disconnected")
            }

            assertTrue(completion.isDone, "Step must not wait for its ordinary timeout: $failurePoint")
            val result = completion.get(1, TimeUnit.SECONDS)
            assertEquals("timeout", result["status"]?.jsonPrimitive?.content)
            assertTrue(result["reason"]!!.jsonPrimitive.content.contains("interrupted: VM disconnected"))
            assertTrue(result["remediation"]!!.jsonPrimitive.content.contains("re-attach the debugger"))
            assertEquals(null, harness.state.activeStep)
            assertEquals(1, harness.disconnectEvents().size)
        }
    }

    @Test
    fun `successful step retires and completes exactly its pending request`() {
        val harness = Harness()
        val request = proxy<StepRequest> { _, _ -> null }
        val completion = CompletableFuture<JsonObject>()
        harness.state.activeStep = PendingStep("step_over", "main", request, completion)

        val resume = harness.threadControlService.handleStepEvent(machine(), stepEvent(request))

        assertFalse(resume)
        assertEquals(null, harness.state.activeStep)
        assertEquals("stopped", completion.get(1, TimeUnit.SECONDS)["status"]?.jsonPrimitive?.content)
        assertTrue(harness.state.suspendedAtMs.containsKey(42L))
    }

    @Test
    fun `mismatched step event does not inspect or replace the pending request`() {
        val harness = Harness()
        val request = proxy<StepRequest> { _, _ -> null }
        val pending = PendingStep("step_over", "main", request, CompletableFuture())
        harness.state.activeStep = pending
        val staleRequest = proxy<StepRequest> { _, _ -> null }
        val event = stepEvent(staleRequest, failurePoint = "event")

        assertTrue(harness.threadControlService.handleStepEvent(machine(), event))
        assertTrue(harness.state.activeStep === pending)
        assertFalse(pending.completion.isDone)
        assertTrue(harness.state.suspendedAtMs.isEmpty())
    }

    @Test
    fun `step retired during payload construction does not overwrite newer state`() {
        for (replacement in listOf(false, true)) {
            val harness = Harness()
            val request = proxy<StepRequest> { _, _ -> null }
            val pending = PendingStep("step_over", "main", request, CompletableFuture())
            val next = PendingStep("step_into", "main", request, CompletableFuture())
            harness.state.activeStep = pending
            val event = stepEvent(request, duringPayload = {
                harness.state.activeStep = if (replacement) next else null
            })

            assertTrue(harness.threadControlService.handleStepEvent(machine(), event))
            assertTrue(harness.state.activeStep === if (replacement) next else null)
            assertFalse(pending.completion.isDone)
            assertFalse(next.completion.isDone)
            assertTrue(harness.state.suspendedAtMs.isEmpty())
        }
    }

    private fun machine(): VirtualMachine {
        val manager = proxy<EventRequestManager> { _, _ -> null }
        return proxy<VirtualMachine> { _, _ -> manager }
    }

    private fun stepEvent(
        request: StepRequest,
        failurePoint: String? = null,
        duringPayload: () -> Unit = {},
    ): StepEvent {
        var idReads = 0
        val thread = proxy<ThreadReference> { method, _ ->
            when (method.name) {
                "frames" -> {
                    duringPayload()
                    emptyList<Any>()
                }
                "name" -> "main"
                "uniqueID" -> {
                    idReads += 1
                    if (failurePoint == "suspension" && idReads == 2) throw VMDisconnectedException()
                    42L
                }
                else -> null
            }
        }
        val type = proxy<ReferenceType> { _, _ -> "example.Target" }
        val method = proxy<com.sun.jdi.Method> { called, _ ->
            when (called.name) {
                "name" -> "work"
                "argumentTypeNames" -> emptyList<String>()
                else -> null
            }
        }
        val location = proxy<Location> { called, _ ->
            if (failurePoint == "location") throw VMDisconnectedException()
            when (called.name) {
                "declaringType" -> type
                "method" -> method
                "lineNumber" -> 12
                else -> null
            }
        }
        return proxy<StepEvent> { called, _ ->
            when (called.name) {
                "request" -> request
                "thread" -> if (failurePoint == "event") throw VMDisconnectedException() else thread
                "location" -> location
                else -> null
            }
        }
    }

    private inline fun <reified T> proxy(
        crossinline handler: (java.lang.reflect.Method, Array<out Any?>?) -> Any?,
    ): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { instance, method, args ->
            when (method.name) {
                "equals" -> instance === args?.get(0)
                "hashCode" -> System.identityHashCode(instance)
                "toString" -> "${T::class.java.simpleName}Double"
                else -> handler(method, args)
            }
        } as T

}
