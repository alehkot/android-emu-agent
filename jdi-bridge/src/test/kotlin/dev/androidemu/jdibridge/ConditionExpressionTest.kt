package dev.androidemu.jdibridge

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class ConditionExpressionTest {

    @Test
    fun `truthy path evaluation supports booleans`() {
        val expression = ConditionExpression.parse("isReady")

        assertTrue(expression.evaluate { path ->
            when (path) {
                "isReady" -> ConditionExpression.RuntimeValue.Bool(true)
                else -> ConditionExpression.RuntimeValue.Null
            }
        })

        assertFalse(expression.evaluate { path ->
            when (path) {
                "isReady" -> ConditionExpression.RuntimeValue.Bool(false)
                else -> ConditionExpression.RuntimeValue.Null
            }
        })
    }

    @Test
    fun `comparison and boolean operators evaluate with precedence`() {
        val expression = ConditionExpression.parse("(attempts >= 3 && isReady) || force")

        val matched =
            expression.evaluate { path ->
                when (path) {
                    "attempts" -> ConditionExpression.RuntimeValue.Number(4.0)
                    "isReady" -> ConditionExpression.RuntimeValue.Bool(true)
                    "force" -> ConditionExpression.RuntimeValue.Bool(false)
                    else -> ConditionExpression.RuntimeValue.Null
                }
            }

        assertTrue(matched)
    }

    @Test
    fun `string and null equality are supported`() {
        val equalsText = ConditionExpression.parse("state == \"LOCKED\"")
        assertTrue(
            equalsText.evaluate { path ->
                if (path == "state") {
                    ConditionExpression.RuntimeValue.Text("LOCKED")
                } else {
                    ConditionExpression.RuntimeValue.Null
                }
            },
        )

        val notNull = ConditionExpression.parse("session != null")
        assertTrue(
            notNull.evaluate { path ->
                if (path == "session") {
                    ConditionExpression.RuntimeValue.Object("com.example.Session")
                } else {
                    ConditionExpression.RuntimeValue.Null
                }
            },
        )
    }

    @Test
    fun `and operator short-circuits right side`() {
        val expression = ConditionExpression.parse("isReady && missing.path")

        val result =
            expression.evaluate { path ->
                when (path) {
                    "isReady" -> ConditionExpression.RuntimeValue.Bool(false)
                    else -> throw AssertionError("Right side should not be evaluated: $path")
                }
            }

        assertFalse(result)
    }

    @Test
    fun `invalid syntax fails parse with condition syntax exception`() {
        val error = assertThrows<ConditionSyntaxException> {
            ConditionExpression.parse("attempts >")
        }

        val message = error.message ?: ""
        assertTrue(message.contains("position") || message.contains("end of expression"))
    }

    @Test
    fun `unsupported method call style token fails parse`() {
        assertThrows<ConditionSyntaxException> {
            ConditionExpression.parse("cart.total() > 1")
        }
    }

    @Test
    fun `numeric comparison rejects non numeric operands`() {
        val expression = ConditionExpression.parse("state > 1")

        val error =
            assertThrows<ConditionEvaluationException> {
                expression.evaluate { path ->
                    if (path == "state") {
                        ConditionExpression.RuntimeValue.Text("LOCKED")
                    } else {
                        ConditionExpression.RuntimeValue.Null
                    }
                }
            }

        assertTrue((error.message ?: "").contains("ERR_CONDITION_TYPE"))
    }
}
