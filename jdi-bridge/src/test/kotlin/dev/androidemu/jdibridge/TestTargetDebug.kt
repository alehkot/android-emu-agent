package dev.androidemu.jdibridge

/**
 * JDWP target focused on stack/inspect/eval tests.
 *
 * The [Helper.tick] method intentionally creates locals and object fields so
 * integration tests can inspect them through JDI.
 */
object TestTargetDebug {
    data class User(val id: Int, val name: String)

    class Helper {
        private var seed: Int = 7

        fun tick() {
            val user = User(seed, "name-$seed")
            val marker = user.id // Breakpoint line used in tests.
            if (marker == -1) {
                println("unreachable")
            }
            seed += 1
        }
    }

    @JvmStatic
    fun main(args: Array<String>) {
        System.err.println("TestTargetDebug ready")
        val helper = Helper()
        while (true) {
            helper.tick()
            Thread.sleep(20)
        }
    }
}
