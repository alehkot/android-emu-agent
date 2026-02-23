package dev.androidemu.jdibridge

/**
 * Target JVM that repeatedly throws and catches an exception.
 */
object TestTargetException {
    @JvmStatic
    fun main(args: Array<String>) {
        System.err.println("TestTargetException ready")
        while (true) {
            try {
                throw IllegalStateException("boom")
            } catch (_: IllegalStateException) {
                // Keep process alive so exception breakpoints can repeatedly trigger.
            }
            Thread.sleep(20)
        }
    }
}
