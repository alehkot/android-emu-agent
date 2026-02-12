package dev.androidemu.jdibridge

import kotlin.math.max

/**
 * Tracks approximate serialized response size as token-equivalent character budget.
 *
 * We approximate 1 token ~= 4 chars to keep payloads bounded without
 * introducing heavyweight tokenization.
 */
class TokenBudget(private val maxTokens: Int = DEFAULT_MAX_TOKENS) {
    companion object {
        const val DEFAULT_MAX_TOKENS = 4000
        private const val CHARS_PER_TOKEN = 4
    }

    private val maxChars: Int = maxTokens * CHARS_PER_TOKEN
    private var usedChars: Int = 0
    var truncated: Boolean = false
        private set

    fun tryConsume(chars: Int): Boolean {
        if (chars <= 0) {
            return true
        }

        val next = usedChars + chars
        if (next > maxChars) {
            truncated = true
            return false
        }

        usedChars = next
        return true
    }

    fun markTruncated() {
        truncated = true
    }

    fun tokenUsageEstimate(): Int {
        if (usedChars <= 0) {
            return 0
        }
        return max(1, (usedChars + CHARS_PER_TOKEN - 1) / CHARS_PER_TOKEN)
    }
}
