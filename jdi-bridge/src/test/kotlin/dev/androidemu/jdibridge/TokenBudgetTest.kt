package dev.androidemu.jdibridge

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TokenBudgetTest {
    @Test
    fun `tracks usage and truncation`() {
        val budget = TokenBudget(maxTokens = 2) // 8 chars

        assertTrue(budget.tryConsume(4))
        assertTrue(budget.tryConsume(4))
        assertFalse(budget.tryConsume(1))
        assertTrue(budget.truncated)
        assertEquals(2, budget.tokenUsageEstimate())
    }

    @Test
    fun `zero usage yields zero tokens`() {
        val budget = TokenBudget()
        assertEquals(0, budget.tokenUsageEstimate())
        assertFalse(budget.truncated)
    }
}
