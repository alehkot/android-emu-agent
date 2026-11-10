package dev.androidemu.jdibridge

/**
 * JDWP target for disconnect tests: the line after the breakpoint sleeps for seconds, so a step
 * over it is still pending when the test stops the VM.
 */
object TestTargetSlowStep {
    @JvmStatic
    fun main(args: Array<String>) {
        var ticks = 0
        while (true) {
            ticks += 1 // Breakpoint line used in tests.
            Thread.sleep(5_000)
        }
    }
}
