package dev.androidemu.jdibridge

/**
 * Simple target JVM that sleeps forever.
 * Launched with JDWP agent for JDI attach tests.
 */
object TestTarget {
    @JvmStatic
    fun main(args: Array<String>) {
        // Signal readiness
        System.err.println("TestTarget ready")
        Thread.sleep(Long.MAX_VALUE)
    }
}
