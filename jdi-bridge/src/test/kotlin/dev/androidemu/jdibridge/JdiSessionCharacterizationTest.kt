package dev.androidemu.jdibridge

import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.Collections
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout

@Timeout(40, unit = TimeUnit.SECONDS)
class JdiSessionCharacterizationTest {

    companion object {
        private const val EXCEPTION_TARGET_CLASS = "dev.androidemu.jdibridge.TestTargetException"
        private const val STEP_TARGET_CLASS = "dev.androidemu.jdibridge.TestTargetDebug"
        private const val STEP_BREAKPOINT_LINE = 30
    }

    @Test
    fun `exception breakpoint hit includes expected payload fields`() {
        val notifications = Collections.synchronizedList(mutableListOf<JsonElement>())
        val session = JdiSession { notifications.add(it) }
        val (process, port) = startTarget(EXCEPTION_TARGET_CLASS)

        try {
            session.attach("localhost", port)
            val set =
                session.setExceptionBreakpoint(
                    classPattern = "java.lang.IllegalStateException",
                    caught = true,
                    uncaught = false,
                ).jsonObject
            val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
            assertTrue(status == "set" || status == "pending")

            val event = waitForEvent(notifications, "exception_hit", timeoutMs = 10_000)
            assertEquals("exception_hit", event["type"]?.jsonPrimitive?.content)
            assertEquals("java.lang.IllegalStateException", event["exception_class"]?.jsonPrimitive?.content)
            assertTrue(event.containsKey("breakpoint_id"))
            assertTrue(event.containsKey("throw_location"))
            assertTrue(event.containsKey("catch_location"))
            assertEquals("stopped", event["status"]?.jsonPrimitive?.content)
            assertEquals("main", event["thread"]?.jsonPrimitive?.content)
        } finally {
            if (session.isAttached) {
                runCatching { session.detach() }
            }
            process.destroyForcibly()
            process.waitFor(5, TimeUnit.SECONDS)
        }
    }

    @Test
    fun `step interrupted by disconnect returns timeout remediation payload`() {
        val notifications = Collections.synchronizedList(mutableListOf<JsonElement>())
        val session = JdiSession { notifications.add(it) }
        val (process, port) = startTarget(STEP_TARGET_CLASS)

        try {
            session.attach("localhost", port, keepSuspended = true)
            val set = session.setBreakpoint(STEP_TARGET_CLASS, STEP_BREAKPOINT_LINE).jsonObject
            val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
            assertTrue(status == "set" || status == "pending")
            session.resume(null)
            if (status == "pending") {
                waitForEvent(notifications, "breakpoint_resolved", timeoutMs = 10_000)
            }

            waitForEvent(notifications, "breakpoint_hit", timeoutMs = 10_000)
            val warmupStep = session.stepOver("main", timeoutSeconds = 10.0).jsonObject
            assertEquals("stopped", warmupStep["status"]?.jsonPrimitive?.content)

            val stepResult = CompletableFuture<JsonObject>()
            val worker =
                Thread {
                    try {
                        stepResult.complete(session.stepOver("main", timeoutSeconds = 20.0).jsonObject)
                    } catch (t: Throwable) {
                        stepResult.completeExceptionally(t)
                    }
                }
            worker.isDaemon = true
            worker.start()

            Thread.sleep(5)
            process.destroyForcibly()
            process.waitFor(5, TimeUnit.SECONDS)

            val result = stepResult.get(15, TimeUnit.SECONDS)
            assertEquals("timeout", result["status"]?.jsonPrimitive?.content)
            val reason = result["reason"]?.jsonPrimitive?.content ?: ""
            assertTrue(reason.contains("interrupted: VM disconnected"))
            val remediation = result["remediation"]?.jsonPrimitive?.content ?: ""
            assertTrue(remediation.contains("re-attach the debugger"))

            val disconnectEvent = waitForEvent(notifications, "vm_disconnected", timeoutMs = 10_000)
            assertEquals("vm_disconnected", disconnectEvent["type"]?.jsonPrimitive?.content)
        } finally {
            if (session.isAttached) {
                runCatching { session.detach() }
            }
            process.destroyForcibly()
            process.waitFor(5, TimeUnit.SECONDS)
        }
    }

    private fun startTarget(mainClass: String): Pair<Process, Int> {
        val javaHome = System.getProperty("java.home")
        val javaBin = "$javaHome/bin/java"
        val classpath = System.getProperty("java.class.path")

        val pb =
            ProcessBuilder(
                javaBin,
                "--add-modules",
                "jdk.jdi",
                "-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=localhost:0",
                "-cp",
                classpath,
                mainClass,
            )
        pb.redirectErrorStream(true)
        val process = pb.start()

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

    private fun waitForEvent(
        notifications: MutableList<JsonElement>,
        type: String,
        timeoutMs: Long,
    ): JsonObject {
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
}
