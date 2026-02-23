package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import org.junit.jupiter.api.assertThrows
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.Collections
import java.util.concurrent.TimeUnit

@Timeout(30, unit = TimeUnit.SECONDS)
class JdiSessionConditionTest {

    companion object {
        private const val MAIN_CLASS = "dev.androidemu.jdibridge.TestTargetDebug"
        private const val MAIN_LOOP_LINE = 30
    }

    private var targetProcess: Process? = null
    private var targetPort: Int = 0
    private lateinit var session: JdiSession
    private val notifications = Collections.synchronizedList(mutableListOf<JsonElement>())

    @BeforeEach
    fun setUp() {
        notifications.clear()
        session = JdiSession { notifications.add(it) }

        val javaHome = System.getProperty("java.home")
        val javaBin = "$javaHome/bin/java"
        val classpath = System.getProperty("java.class.path")

        val processBuilder = ProcessBuilder(
            javaBin,
            "--add-modules", "jdk.jdi",
            "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=localhost:0",
            "-cp", classpath,
            MAIN_CLASS,
        )
        processBuilder.redirectErrorStream(true)
        val proc = processBuilder.start()
        targetProcess = proc

        val reader = BufferedReader(InputStreamReader(proc.inputStream))
        var jdwpLine: String? = null
        for (i in 0 until 40) {
            val line = reader.readLine() ?: break
            if (line.contains("Listening for transport")) {
                jdwpLine = line
                break
            }
        }
        val line = jdwpLine ?: throw IllegalStateException("TestTargetDebug did not output JDWP address")
        val portStr = line.substringAfterLast(":").trim()
        targetPort =
            portStr.toIntOrNull()
                ?: throw IllegalStateException("Could not parse port from: $line")
    }

    @AfterEach
    fun tearDown() {
        if (session.isAttached) {
            try {
                session.detach()
            } catch (_: Exception) {
                // Best effort cleanup
            }
        }
        targetProcess?.destroyForcibly()
        targetProcess?.waitFor(5, TimeUnit.SECONDS)
    }

    @Test
    fun `set breakpoint rejects malformed condition syntax`() {
        session.attach("localhost", targetPort)

        val error =
            assertThrows<RpcException> {
                session.setBreakpoint(MAIN_CLASS, MAIN_LOOP_LINE, condition = "attempts >")
            }

        assertEquals(INVALID_PARAMS, error.code)
        assertTrue((error.message ?: "").contains("ERR_CONDITION_SYNTAX"))
    }

    @Test
    fun `condition metadata is preserved in breakpoint list`() {
        session.attach("localhost", targetPort)

        setConditionBreakpoint("helper.seed >= 7")

        val listed = session.listBreakpoints().jsonObject
        val breakpoints = listed["breakpoints"]?.jsonArray
        val condition = breakpoints?.firstOrNull()?.jsonObject?.get("condition")?.jsonPrimitive?.content
        assertEquals("helper.seed >= 7", condition)
    }

    @Test
    fun `true condition suspends and emits breakpoint hit`() {
        session.attach("localhost", targetPort)
        notifications.clear()

        setConditionBreakpoint("helper.seed >= 7")
        session.resume(null)
        waitForMainSuspended(timeoutMs = 10_000)

        val event = waitForEvent("breakpoint_hit", timeoutMs = 10_000)
        assertEquals("helper.seed >= 7", event["condition"]?.jsonPrimitive?.content)
    }

    @Test
    fun `false condition auto resumes without breakpoint hit`() {
        session.attach("localhost", targetPort)
        notifications.clear()

        setConditionBreakpoint("helper.seed < 0")
        session.resume(null)

        Thread.sleep(500)
        assertMainNotSuspended()

        val types = allEventTypes()
        assertFalse(types.contains("breakpoint_hit"))
        assertFalse(types.contains("breakpoint_condition_error"))
    }

    @Test
    fun `condition runtime errors emit event and continue running`() {
        session.attach("localhost", targetPort)
        notifications.clear()

        setConditionBreakpoint("missingVar > 0")
        session.resume(null)

        val event = waitForEvent("breakpoint_condition_error", timeoutMs = 10_000)
        assertTrue((event["error"]?.jsonPrimitive?.content ?: "").contains("missingVar"))
        assertMainNotSuspended()
    }

    private fun waitForMainSuspended(timeoutMs: Long) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            try {
                session.inspectVariable(
                    threadName = "main",
                    frameIndex = 0,
                    variablePath = "helper",
                    depth = 1,
                )
                return
            } catch (_: RpcException) {
                Thread.sleep(50)
            }
        }
        throw AssertionError("Timed out waiting for main thread suspension")
    }

    private fun setConditionBreakpoint(condition: String) {
        val set =
            session.setBreakpoint(
                MAIN_CLASS,
                MAIN_LOOP_LINE,
                condition = condition,
            ).jsonObject
        val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
        assertTrue(status == "set" || status == "pending")
        if (status == "pending") {
            waitForEvent("breakpoint_resolved", timeoutMs = 10_000)
        }
    }

    private fun assertMainNotSuspended(timeoutMs: Long = 2_000) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val error =
                assertThrows<RpcException> {
                    session.inspectVariable(
                        threadName = "main",
                        frameIndex = 0,
                        variablePath = "helper",
                        depth = 1,
                    )
                }
            if ((error.message ?: "").contains("ERR_NOT_SUSPENDED")) {
                return
            }
            Thread.sleep(25)
        }
        throw AssertionError("Expected main thread to be running (not suspended)")
    }

    private fun waitForEvent(type: String, timeoutMs: Long): JsonObject {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            synchronized(notifications) {
                for (entry in notifications) {
                    val params = entry.jsonObject["params"]?.jsonObject ?: continue
                    val eventType = params["type"]?.jsonPrimitive?.content ?: continue
                    if (eventType == type) {
                        return params
                    }
                }
            }
            Thread.sleep(25)
        }
        throw AssertionError("Timed out waiting for event '$type'")
    }

    private fun allEventTypes(): Set<String> {
        synchronized(notifications) {
            return notifications
                .mapNotNull { it.jsonObject["params"]?.jsonObject?.get("type")?.jsonPrimitive?.content }
                .toSet()
        }
    }
}
