package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Assertions.fail
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import org.junit.jupiter.api.assertThrows
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

@Timeout(30, unit = TimeUnit.SECONDS)
class JdiSessionMilestone4Test {

    companion object {
        private const val MAIN_CLASS = "dev.androidemu.jdibridge.TestTargetDebug"
        private const val MAIN_LOOP_LINE = 30
    }

    private data class LocalContext(
        val localName: String,
        val firstField: String?,
    )

    private var targetProcess: Process? = null
    private var targetPort: Int = 0
    private lateinit var session: JdiSession

    @BeforeEach
    fun setUp() {
        session = JdiSession { /* notifications are not required in these tests */ }

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
        targetPort = portStr.toIntOrNull()
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
    fun `stack trace respects max_frames and truncation fields`() {
        attachAndPauseAtMainLoop()

        val result = session.stackTrace(threadName = "main", maxFrames = 1).jsonObject
        assertEquals("main", result["thread"]?.jsonPrimitive?.content)
        assertEquals(1, result["max_frames"]?.jsonPrimitive?.int)

        val shown = result["shown_frames"]?.jsonPrimitive?.int ?: 0
        val total = result["total_frames"]?.jsonPrimitive?.int ?: 0
        val truncated = result["truncated"]?.jsonPrimitive?.boolean ?: false
        assertEquals(1, shown)
        assertTrue(total >= shown)
        assertEquals(total > shown, truncated)
    }

    @Test
    fun `inspect variable returns nested data and object id`() {
        val context = attachAndPauseAtMainLoop()

        val result = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = context.localName,
            depth = 2,
        ).jsonObject

        assertEquals(context.localName, result["variable_path"]?.jsonPrimitive?.content)
        val value = result["value"]?.jsonObject ?: fail("Expected object value payload")
        assertTrue(value.containsKey("object_id"))
        val fields = value["fields"]?.jsonObject ?: fail("Expected fields payload")
        assertTrue(fields.isNotEmpty())

        val nestedField = context.firstField ?: fields.keys.first()
        val nested = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = "${context.localName}.$nestedField",
            depth = 1,
        ).jsonObject
        assertTrue(nested.containsKey("value"))
    }

    @Test
    fun `evaluate supports field access and toString only`() {
        val context = attachAndPauseAtMainLoop()

        val fieldPath = context.firstField?.let { "${context.localName}.$it" } ?: context.localName
        val fieldEval = session.evaluate(
            threadName = "main",
            frameIndex = 0,
            expression = fieldPath,
        ).jsonObject
        assertEquals(fieldPath, fieldEval["expression"]?.jsonPrimitive?.content)
        assertTrue(fieldEval.containsKey("result"))

        val toStringEval = session.evaluate(
            threadName = "main",
            frameIndex = 0,
            expression = "${context.localName}.toString()",
        ).jsonObject
        val toStringResult = toStringEval["result"]?.jsonPrimitive?.content ?: ""
        assertTrue(toStringResult.isNotBlank())

        val unsupported = assertThrows<RpcException> {
            session.evaluate(
                threadName = "main",
                frameIndex = 0,
                expression = "${context.localName}.hashCode()",
            )
        }
        assertTrue((unsupported.message ?: "").contains("ERR_EVAL_UNSUPPORTED"))
    }

    @Test
    fun `object ids are invalidated after resume`() {
        val context = attachAndPauseAtMainLoop()

        val inspected = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = context.localName,
            depth = 1,
        ).jsonObject
        val objectId = inspected["value"]
            ?.jsonObject
            ?.get("object_id")
            ?.jsonPrimitive
            ?.content
            ?: fail("Expected object_id in inspect response")

        session.resume("main")
        waitForSuspendedHelper(timeoutMs = 10_000)

        val stale = assertThrows<RpcException> {
            session.inspectVariable(
                threadName = "main",
                frameIndex = 0,
                variablePath = objectId,
                depth = 1,
            )
        }
        assertTrue((stale.message ?: "").contains("ERR_OBJECT_COLLECTED"))
    }

    private fun attachAndPauseAtMainLoop(): LocalContext {
        session.attach("localhost", targetPort)
        val set = session.setBreakpoint(MAIN_CLASS, MAIN_LOOP_LINE).jsonObject
        val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
        assertTrue(status == "set" || status == "pending")

        session.resume(null)
        return waitForSuspendedHelper(timeoutMs = 10_000)
    }

    private fun waitForSuspendedHelper(timeoutMs: Long): LocalContext {
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastReason = "none"
        while (System.currentTimeMillis() < deadline) {
            try {
                val inspected = session.inspectVariable(
                    threadName = "main",
                    frameIndex = 0,
                    variablePath = "helper",
                    depth = 1,
                ).jsonObject
                val rawValue = inspected["value"]
                if (rawValue !is JsonObject) {
                    lastReason = "helper value not object"
                    Thread.sleep(50)
                    continue
                }
                val value = rawValue
                val fields = value["fields"] as? JsonObject
                val firstField = fields?.keys?.firstOrNull()
                return LocalContext(localName = "helper", firstField = firstField)
            } catch (exc: RpcException) {
                lastReason = exc.message ?: "rpc error"
                Thread.sleep(50)
            }
        }
        throw AssertionError("Timed out waiting for helper to become inspectable ($lastReason)")
    }
}
