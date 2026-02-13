package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.Timeout
import java.io.BufferedReader
import java.io.InputStreamReader
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.TimeUnit

@Timeout(30, unit = TimeUnit.SECONDS)
class JdiSessionMilestone5Test {

    companion object {
        private const val MAIN_CLASS = "dev.androidemu.jdibridge.TestTargetDebug"
        private const val MAIN_LOOP_LINE = 30
        private const val HELPER_CLASS = "dev.androidemu.jdibridge.TestTargetDebug\$Helper"
        private const val DEOBF_MAIN_CLASS = "com.example.AppEntry"
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
    fun `stack trace class and method names are deobfuscated when mapping is loaded`() {
        attachAndPauseAtMainLoop()

        val plainFrames = session.stackTrace(threadName = "main", maxFrames = 10)
            .jsonObject["frames"]!!.jsonArray
        val plainFrame = firstFrameByClass(plainFrames, MAIN_CLASS)
        assertNotNull(plainFrame)
        assertEquals("main", plainFrame?.get("method")?.jsonPrimitive?.content)

        val mappingPath = writeMappingFile()
        val load = session.loadMapping(mappingPath.toString()).jsonObject
        assertEquals("loaded", load["status"]?.jsonPrimitive?.content)

        val mappedFrames = session.stackTrace(threadName = "main", maxFrames = 10)
            .jsonObject["frames"]!!.jsonArray
        val mappedFrame = firstFrameByClass(mappedFrames, DEOBF_MAIN_CLASS)
        assertNotNull(mappedFrame)
        assertEquals("launch", mappedFrame?.get("method")?.jsonPrimitive?.content)
    }

    @Test
    fun `inspect output and variable path use deobfuscated field names`() {
        attachAndPauseAtMainLoop()
        val mappingPath = writeMappingFile()
        session.loadMapping(mappingPath.toString())

        val mapped = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = "helper",
            depth = 2,
        ).jsonObject
        val mappedFields = mapped["value"]
            ?.jsonObject
            ?.get("fields")
            ?.jsonObject
            ?: throw AssertionError("Expected mapped object fields")
        assertTrue(mappedFields.containsKey("profileId"))
        assertFalse(mappedFields.containsKey("seed"))

        val nested = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = "helper.profileId",
            depth = 1,
        ).jsonObject
        assertTrue(nested.containsKey("value"))

        session.clearMapping()
        val plain = session.inspectVariable(
            threadName = "main",
            frameIndex = 0,
            variablePath = "helper",
            depth = 2,
        ).jsonObject
        val plainFields = plain["value"]
            ?.jsonObject
            ?.get("fields")
            ?.jsonObject
            ?: throw AssertionError("Expected plain object fields")
        assertTrue(plainFields.containsKey("seed"))
    }

    private fun attachAndPauseAtMainLoop() {
        session.attach("localhost", targetPort)
        val set = session.setBreakpoint(MAIN_CLASS, MAIN_LOOP_LINE).jsonObject
        val status = set["status"]?.jsonPrimitive?.content ?: "unknown"
        assertTrue(status == "set" || status == "pending")
        session.resume(null)
        waitForSuspendedAtHelper(timeoutMs = 10_000)
    }

    private fun waitForSuspendedAtHelper(timeoutMs: Long) {
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
        throw AssertionError("Timed out waiting for helper local to become inspectable")
    }

    private fun writeMappingFile(): Path {
        val path = Files.createTempFile("jdibridge-", "-mapping.txt")
        Files.writeString(
            path,
            """
            com.example.AppEntry -> dev.androidemu.jdibridge.TestTargetDebug:
                void launch(java.lang.String[]) -> main
            com.example.UserService -> dev.androidemu.jdibridge.TestTargetDebug${'$'}Helper:
                int profileId -> seed
                void fetchProfile() -> tick
            """.trimIndent(),
            StandardCharsets.UTF_8,
        )
        return path
    }

    private fun firstFrameByClass(
        frames: kotlinx.serialization.json.JsonArray,
        className: String,
    ): JsonObject? {
        return frames
            .mapNotNull { it as? JsonObject }
            .firstOrNull { frame ->
                frame["class"]?.jsonPrimitive?.content == className
            }
    }
}
