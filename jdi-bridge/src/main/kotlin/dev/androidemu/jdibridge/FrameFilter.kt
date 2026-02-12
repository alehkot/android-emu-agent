package dev.androidemu.jdibridge

import com.sun.jdi.Location

/**
 * Filters noisy coroutine/internal runtime frames so debugger output stays focused on user code.
 */
object FrameFilter {
    data class Selection(
        val selectedIndex: Int,
        val filteredCount: Int,
    )

    fun selectPrimaryFrame(locations: List<Location>): Selection {
        var filtered = 0
        for ((index, location) in locations.withIndex()) {
            if (isCoroutineInternal(location)) {
                filtered += 1
                continue
            }
            return Selection(selectedIndex = index, filteredCount = filtered)
        }

        return Selection(selectedIndex = 0, filteredCount = filtered)
    }

    fun isCoroutineInternal(location: Location): Boolean {
        val className = location.declaringType().name()
        val methodName = location.method().name()

        if (className == "kotlin.coroutines.jvm.internal.BaseContinuationImpl" &&
            methodName == "resumeWith"
        ) {
            return true
        }

        if (className.startsWith("kotlinx.coroutines.DispatchedTask") && methodName == "run") {
            return true
        }

        if (methodName.contains("invokeSuspend")) {
            return true
        }

        if (className.contains("CoroutineScheduler")) {
            return true
        }

        return false
    }
}
