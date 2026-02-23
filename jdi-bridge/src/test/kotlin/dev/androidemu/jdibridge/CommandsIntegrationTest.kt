package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.Collections
import java.util.concurrent.TimeUnit

@Timeout(40, unit = TimeUnit.SECONDS)
class CommandsIntegrationTest {

    companion object {
        private const val MAIN_CLASS = "dev.androidemu.jdibridge.TestTargetDebug"
        private const val MAIN_LOOP_LINE = 30
    }

    private var targetProcess: Process? = null
    private var targetPort: Int = 0
    private var nextRequestId = 1
    private val notifications = Collections.synchronizedList(mutableListOf<JsonElement>())

    @BeforeEach
    fun setUp() {
        notifications.clear()
        nextRequestId = 1
        Commands.init { notifications.add(it) }
        val (process, port) = startTarget(MAIN_CLASS)
        targetProcess = process
        targetPort = port
    }

    @AfterEach
    fun tearDown() {
        runCatching { rpcResult("detach") }
        targetProcess?.destroyForcibly()
        targetProcess?.waitFor(5, TimeUnit.SECONDS)
    }

    @Test
    fun `commands route step into and out`() {
        rpcResult(
            "attach",
            """{"host":"localhost","port":$targetPort,"keep_suspended":true}""",
        )

        val set =
            rpcResult(
                "set_breakpoint",
                """{"class_pattern":"$MAIN_CLASS","line":$MAIN_LOOP_LINE}""",
            )
        val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
        assertTrue(status == "set" || status == "pending")
        if (status == "pending") {
            waitForEvent("breakpoint_resolved", timeoutMs = 10_000)
        }

        rpcResult("resume", "{}")
        waitForEvent("breakpoint_hit", timeoutMs = 10_000)

        val stepInto = rpcResult("step_into", """{"thread_name":"main","timeout_seconds":10.0}""")
        assertEquals("stopped", stepInto["status"]?.jsonPrimitive?.content)

        val stepOut = rpcResult("step_out", """{"thread_name":"main","timeout_seconds":10.0}""")
        assertEquals("stopped", stepOut["status"]?.jsonPrimitive?.content)
    }

    @Test
    fun `commands route exception breakpoint lifecycle`() {
        rpcResult(
            "attach",
            """{"host":"localhost","port":$targetPort,"keep_suspended":true}""",
        )

        val set =
            rpcResult(
                "set_exception_breakpoint",
                """{"class_pattern":"*","caught":true,"uncaught":false}""",
            )
        val breakpointId = set["breakpoint_id"]?.jsonPrimitive?.int
            ?: throw AssertionError("Missing exception breakpoint_id")
        assertEquals("set", set["status"]?.jsonPrimitive?.content)
        assertEquals("*", set["class_pattern"]?.jsonPrimitive?.content)

        val listed = rpcResult("list_exception_breakpoints")
        assertEquals(1, listed["count"]?.jsonPrimitive?.int)
        val entries = listed["exception_breakpoints"]?.jsonArray
            ?: throw AssertionError("Missing exception_breakpoints array")
        assertEquals(1, entries.size)
        val first = entries.first().jsonObject
        assertEquals(breakpointId, first["breakpoint_id"]?.jsonPrimitive?.int)
        assertEquals("*", first["class_pattern"]?.jsonPrimitive?.content)
        assertEquals(true, first["caught"]?.jsonPrimitive?.content?.toBooleanStrictOrNull())
        assertEquals(false, first["uncaught"]?.jsonPrimitive?.content?.toBooleanStrictOrNull())

        val removed =
            rpcResult(
                "remove_exception_breakpoint",
                """{"breakpoint_id":$breakpointId}""",
            )
        assertEquals("removed", removed["status"]?.jsonPrimitive?.content)
        assertEquals(breakpointId, removed["breakpoint_id"]?.jsonPrimitive?.int)

        val after = rpcResult("list_exception_breakpoints")
        assertEquals(0, after["count"]?.jsonPrimitive?.int)
    }

    private fun rpcResult(method: String, paramsJson: String = "{}"): JsonObject {
        val response = rpc(method, paramsJson)
        val error = response["error"]
        if (error != null && error !is JsonNull) {
            throw AssertionError("Unexpected RPC error for method '$method': $error")
        }
        return response["result"]?.jsonObject
            ?: throw AssertionError("Missing result payload for method '$method'")
    }

    private fun rpc(method: String, paramsJson: String): JsonObject {
        val requestId = nextRequestId++
        val request =
            """{"jsonrpc":"2.0","id":$requestId,"method":"$method","params":$paramsJson}"""
        val raw = handleLine(request)
            ?: throw AssertionError("No response for method '$method'")
        return json.parseToJsonElement(raw).jsonObject
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

    private fun startTarget(mainClass: String): Pair<Process, Int> {
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
                mainClass,
            )
        processBuilder.redirectErrorStream(true)
        val process = processBuilder.start()

        val reader = BufferedReader(InputStreamReader(process.inputStream))
        var jdwpLine: String? = null
        for (i in 0 until 40) {
            val line = reader.readLine() ?: break
            if (line.contains("Listening for transport")) {
                jdwpLine = line
                break
            }
        }

        val line = jdwpLine ?: throw IllegalStateException("$mainClass did not output JDWP address")
        val port =
            line.substringAfterLast(":").trim().toIntOrNull()
                ?: throw IllegalStateException("Could not parse port from: $line")
        return process to port
    }
}
