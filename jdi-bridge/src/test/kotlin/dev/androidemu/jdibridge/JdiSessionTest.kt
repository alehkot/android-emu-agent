package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonElement
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
    fun `status after attach returns attached`() {
        session.attach("localhost", targetPort)
        val status = session.status().jsonObject
        assertEquals("attached", status["status"]?.jsonPrimitive?.content)
        assertTrue(status.containsKey("vm_name"))
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
