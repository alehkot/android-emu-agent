package dev.androidemu.jdibridge

import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

@Timeout(30, unit = TimeUnit.SECONDS)
class JdiSessionInspectorCollectionTest {

    companion object {
        private const val MAIN_CLASS = "dev.androidemu.jdibridge.TestTargetCollections"
        private const val MAIN_LOOP_LINE = 23
    }

    private var targetProcess: Process? = null
    private var targetPort: Int = 0
    private lateinit var session: JdiSession

    @BeforeEach
    fun setUp() {
        session = JdiSession { }

        val javaHome = System.getProperty("java.home")
        val javaBin = "$javaHome/bin/java"
        val classpath = System.getProperty("java.class.path")

        val processBuilder =
            ProcessBuilder(
                javaBin,
                "--add-modules",
                "jdk.jdi",
                "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=localhost:0",
                "-cp",
                classpath,
                MAIN_CLASS,
            )
        processBuilder.redirectErrorStream(true)
        val process = processBuilder.start()
        targetProcess = process

        val reader = BufferedReader(InputStreamReader(process.inputStream))
        var jdwpLine: String? = null
        for (i in 0 until 40) {
            val line = reader.readLine() ?: break
            if (line.contains("Listening for transport")) {
                jdwpLine = line
                break
            }
        }

        val line = jdwpLine ?: throw IllegalStateException("TestTargetCollections did not output JDWP address")
        val portStr = line.substringAfterLast(":").trim()
        targetPort =
            portStr.toIntOrNull()
                ?: throw IllegalStateException("Could not parse port from: $line")
    }

    @AfterEach
    fun tearDown() {
        if (session.isAttached) {
            runCatching { session.detach() }
        }
        targetProcess?.destroyForcibly()
        targetProcess?.waitFor(5, TimeUnit.SECONDS)
    }

    @Test
    fun `inspect variable serializes list-like objects with items`() {
        session.attach("localhost", targetPort)
        val set = session.setBreakpoint(MAIN_CLASS, MAIN_LOOP_LINE).jsonObject
        val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
        assertTrue(status == "set" || status == "pending")

        session.resume(null)
        waitForMainSuspended(timeoutMs = 10_000)

        val inspected =
            session.inspectVariable(
                threadName = "main",
                frameIndex = 0,
                variablePath = "helper.values",
                depth = 2,
            ).jsonObject

        val value = inspected["value"]?.jsonObject
            ?: throw AssertionError("Expected inspected value object")
        val className = value["class"]?.jsonPrimitive?.content ?: ""
        assertTrue(className.startsWith("java.util."))
        assertTrue(className.contains("List") || className.contains("ArrayList"))

        val length = value["length"]?.jsonPrimitive?.int ?: -1
        val items = value["items"]?.jsonArray ?: throw AssertionError("Expected list items")
        assertTrue(length >= 0, "Expected non-negative collection length")
        assertTrue(items.isNotEmpty(), "Expected non-empty serialized list items")
    }

    private fun waitForMainSuspended(timeoutMs: Long) {
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastReason = "none"
        while (System.currentTimeMillis() < deadline) {
            try {
                session.inspectVariable(
                    threadName = "main",
                    frameIndex = 0,
                    variablePath = "helper",
                    depth = 1,
                )
                return
            } catch (exc: RpcException) {
                lastReason = exc.message ?: "rpc error"
                Thread.sleep(50)
            }
        }
        throw AssertionError("Timed out waiting for helper to become inspectable ($lastReason)")
    }
}
