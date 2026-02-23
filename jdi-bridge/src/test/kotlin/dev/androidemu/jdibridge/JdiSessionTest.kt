package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.int
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import org.junit.jupiter.api.assertThrows
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

@Timeout(30, unit = TimeUnit.SECONDS)
class JdiSessionTest {

    private var targetProcess: Process? = null
    private var targetPort: Int = 0
    private val notifications = mutableListOf<JsonElement>()
    private lateinit var session: JdiSession

    @BeforeEach
    fun setUp() {
        notifications.clear()
        session = JdiSession { notifications.add(it) }

        val javaHome = System.getProperty("java.home")
        val javaBin = "$javaHome/bin/java"
        val classpath = System.getProperty("java.class.path")

        // Note: JDWP "Listening" message goes to stdout on some JDKs,
        // stderr on others. Merge them to reliably capture it.
        val pb = ProcessBuilder(
            javaBin,
            "--add-modules", "jdk.jdi",
            "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=localhost:0",
            "-cp", classpath,
            "dev.androidemu.jdibridge.TestTarget"
        )
        pb.redirectErrorStream(true)
        val proc = pb.start()
        targetProcess = proc

        // Parse JDWP port from "Listening for transport dt_socket at address: <port>"
        val reader = BufferedReader(InputStreamReader(proc.inputStream))
        var jdwpLine: String? = null
        // Read up to 20 lines looking for the JDWP message
        for (i in 0 until 20) {
            val line = reader.readLine() ?: break
            if (line.contains("Listening for transport")) {
                jdwpLine = line
                break
            }
        }

        val line = jdwpLine
            ?: throw IllegalStateException("TestTarget did not output JDWP address")

        val portStr = line.substringAfterLast(":").trim()
        targetPort = portStr.toIntOrNull()
            ?: throw IllegalStateException("Could not parse port from: $line")
    }

    @AfterEach
    fun tearDown() {
        if (session.isAttached) {
            try { session.detach() } catch (_: Exception) {}
        }
        targetProcess?.destroyForcibly()
        targetProcess?.waitFor(5, TimeUnit.SECONDS)
    }

    @Test
    fun `attach returns vm info`() {
        val result = session.attach("localhost", targetPort)
        val obj = result.jsonObject

        assertEquals("attached", obj["status"]?.jsonPrimitive?.content)
        assertTrue(obj.containsKey("vm_name"))
        assertTrue(obj.containsKey("vm_version"))
        assertTrue(obj.containsKey("thread_count"))
        assertTrue(session.isAttached)
    }

    @Test
    fun `attach resumes fully suspended vm by default`() {
        val result = session.attach("localhost", targetPort).jsonObject
        val keepSuspended = result["keep_suspended"]?.jsonPrimitive?.booleanOrNull
        assertEquals(false, keepSuspended)
    }

    @Test
    fun `attach can keep vm suspended`() {
        val result = session.attach("localhost", targetPort, keepSuspended = true).jsonObject
        val keepSuspended = result["keep_suspended"]?.jsonPrimitive?.booleanOrNull
        assertEquals(true, keepSuspended)
    }

    @Test
    fun `status after attach returns attached`() {
        session.attach("localhost", targetPort)
        val status = session.status().jsonObject
        assertEquals("attached", status["status"]?.jsonPrimitive?.content)
        assertTrue(status.containsKey("vm_name"))
    }

    @Test
    fun `list threads returns bounded thread payload`() {
        session.attach("localhost", targetPort)

        val result = session.listThreads(includeDaemon = false, maxThreads = 20).jsonObject
        assertTrue(result.containsKey("threads"))
        assertTrue(result.containsKey("total_threads"))
        assertTrue(result.containsKey("truncated"))
    }

    @Test
    fun `breakpoint lifecycle set list remove`() {
        session.attach("localhost", targetPort)

        val set = session.setBreakpoint("dev.androidemu.jdibridge.TestTarget", 12).jsonObject
        val breakpointId = set["breakpoint_id"]?.jsonPrimitive?.int
        assertNotNull(breakpointId)
        val nonNullBreakpointId = breakpointId
            ?: throw IllegalStateException("breakpoint_id missing from setBreakpoint result")
        val status = set["status"]?.jsonPrimitive?.content
        assertTrue(status == "set" || status == "pending")

        val listed = session.listBreakpoints().jsonObject
        val count = listed["count"]?.jsonPrimitive?.int
        assertEquals(1, count)

        val removed = session.removeBreakpoint(nonNullBreakpointId).jsonObject
        assertEquals("removed", removed["status"]?.jsonPrimitive?.content)

        val after = session.listBreakpoints().jsonObject
        assertEquals(0, after["count"]?.jsonPrimitive?.int)
    }

    @Test
    fun `logpoint breakpoint persists stack capture settings`() {
        session.attach("localhost", targetPort)

        val set =
            session.setBreakpoint(
                "dev.androidemu.jdibridge.TestTarget",
                12,
                logMessage = "hit={hitCount}",
                captureStack = true,
                stackMaxFrames = 6,
            ).jsonObject
        val status = set["status"]?.jsonPrimitive?.content
        assertTrue(status == "set" || status == "pending")
        assertEquals("hit={hitCount}", set["log_message"]?.jsonPrimitive?.content)
        assertEquals(true, set["capture_stack"]?.jsonPrimitive?.booleanOrNull)
        assertEquals(6, set["stack_max_frames"]?.jsonPrimitive?.int)

        val listed = session.listBreakpoints().jsonObject
        val breakpoints = listed["breakpoints"]?.jsonArray
        assertNotNull(breakpoints)
        val bp = breakpoints?.firstOrNull()?.jsonObject
        assertEquals("hit={hitCount}", bp?.get("log_message")?.jsonPrimitive?.content)
        assertEquals(true, bp?.get("capture_stack")?.jsonPrimitive?.booleanOrNull)
        assertEquals(6, bp?.get("stack_max_frames")?.jsonPrimitive?.int)
    }

    @Test
    fun `breakpoint condition is preserved in list output`() {
        session.attach("localhost", targetPort)

        val set =
            session.setBreakpoint(
                "dev.androidemu.jdibridge.TestTarget",
                12,
                condition = "isReady || retries >= 2",
            ).jsonObject
        val status = set["status"]?.jsonPrimitive?.content
        assertTrue(status == "set" || status == "pending")

        val listed = session.listBreakpoints().jsonObject
        val breakpoints = listed["breakpoints"]?.jsonArray
        val bp = breakpoints?.firstOrNull()?.jsonObject
        assertEquals("isReady || retries >= 2", bp?.get("condition")?.jsonPrimitive?.content)
    }

    @Test
    fun `malformed breakpoint condition is rejected at set time`() {
        session.attach("localhost", targetPort)

        val error = assertThrows<RpcException> {
            session.setBreakpoint(
                "dev.androidemu.jdibridge.TestTarget",
                12,
                condition = "retries >",
            )
        }
        assertEquals(INVALID_PARAMS, error.code)
        assertTrue((error.message ?: "").contains("ERR_CONDITION_SYNTAX"))
    }

    @Test
    fun `detach after attach succeeds`() {
        session.attach("localhost", targetPort)
        assertTrue(session.isAttached)

        val result = session.detach().jsonObject
        assertEquals("detached", result["status"]?.jsonPrimitive?.content)
        assertFalse(session.isAttached)
    }

    @Test
    fun `double attach throws`() {
        session.attach("localhost", targetPort)
        val ex = assertThrows<RpcException> {
            session.attach("localhost", targetPort)
        }
        assertTrue(ex.message.contains("Already attached"))
    }

    @Test
    fun `detach when not attached throws`() {
        assertFalse(session.isAttached)
        val ex = assertThrows<RpcException> {
            session.detach()
        }
        assertTrue(ex.message.contains("Not attached"))
    }

    @Test
    fun `status when not attached returns not_attached`() {
        val status = session.status().jsonObject
        assertEquals("not_attached", status["status"]?.jsonPrimitive?.content)
    }

    @Test
    fun `vm disconnect triggers notification`() {
        session.attach("localhost", targetPort)
        assertTrue(session.isAttached)

        // Kill the target to trigger VMDisconnect
        targetProcess?.destroyForcibly()
        targetProcess?.waitFor(5, TimeUnit.SECONDS)

        // Poll for disconnect detection (watchdog polls every 500ms)
        val deadline = System.currentTimeMillis() + 10_000
        while (session.isAttached && System.currentTimeMillis() < deadline) {
            Thread.sleep(200)
        }

        assertFalse(session.isAttached, "Session should be disconnected after target kill")
        assertTrue(notifications.isNotEmpty(), "Expected a vm_disconnected notification")
        val notif = notifications.first().jsonObject
        assertEquals("event", notif["method"]?.jsonPrimitive?.content)
        val params = notif["params"]?.jsonObject
        assertEquals("vm_disconnected", params?.get("type")?.jsonPrimitive?.content)
    }
}
