package dev.androidemu.jdibridge

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

        init {
            val inspector = Inspector()
            val frameValueService = JdiFrameValueService(state, inspector)
            val threadControlService = JdiThreadControlService(state, frameValueService)
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
}
