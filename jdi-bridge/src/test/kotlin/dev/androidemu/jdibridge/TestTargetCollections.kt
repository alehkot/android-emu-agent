package dev.androidemu.jdibridge

/**
 * JDWP target focused on collection/list inspection behavior.
 */
object TestTargetCollections {
    class Helper {
        private val values = mutableListOf(1, 2, 3)

        fun tick() {
            values.add(values.size + 1)
            if (values.size > 6) {
                values.removeAt(0)
            }
        }
    }

    @JvmStatic
    fun main(args: Array<String>) {
        System.err.println("TestTargetCollections ready")
        val helper = Helper()
        while (true) {
            helper.tick()
            Thread.sleep(20)
        }
    }
}
