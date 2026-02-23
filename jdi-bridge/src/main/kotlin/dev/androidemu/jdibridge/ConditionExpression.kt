package dev.androidemu.jdibridge

/**
 * Parser/evaluator for conditional breakpoint expressions.
 *
 * Supported syntax:
 * - Boolean operators: &&, ||, !
 * - Comparisons: ==, !=, >, >=, <, <=
 * - Parentheses for grouping
 * - Literals: null, true, false, numbers, strings
 * - Value paths: local or field path (for example user.id)
 */
internal class ConditionExpression private constructor(
    private val source: String,
    private val root: Node,
) {
    sealed interface RuntimeValue {
        data object Null : RuntimeValue

        data class Bool(val value: Boolean) : RuntimeValue

        data class Number(val value: Double) : RuntimeValue

        data class Text(val value: String) : RuntimeValue

        data class Object(val typeName: String? = null) : RuntimeValue
    }

    companion object {
        fun parse(raw: String): ConditionExpression {
            val trimmed = raw.trim()
            if (trimmed.isEmpty()) {
                throw ConditionSyntaxException("condition must not be blank")
            }
            val parser = Parser(trimmed)
            val expression = parser.parseExpression()
            parser.expectEnd()
            return ConditionExpression(trimmed, expression)
        }
    }

    fun evaluate(resolvePath: (String) -> RuntimeValue): Boolean {
        val value = evaluateNode(root, resolvePath)
        return isTruthy(value)
    }

    private fun evaluateNode(node: Node, resolvePath: (String) -> RuntimeValue): RuntimeValue {
        return when (node) {
            is Node.Path -> resolvePath(node.path)
            is Node.Literal -> node.value
            is Node.Not -> RuntimeValue.Bool(!isTruthy(evaluateNode(node.expr, resolvePath)))
            is Node.And -> {
                val left = evaluateNode(node.left, resolvePath)
                if (!isTruthy(left)) {
                    RuntimeValue.Bool(false)
                } else {
                    RuntimeValue.Bool(isTruthy(evaluateNode(node.right, resolvePath)))
                }
            }
            is Node.Or -> {
                val left = evaluateNode(node.left, resolvePath)
                if (isTruthy(left)) {
                    RuntimeValue.Bool(true)
                } else {
                    RuntimeValue.Bool(isTruthy(evaluateNode(node.right, resolvePath)))
                }
            }
            is Node.Compare -> RuntimeValue.Bool(compare(node.operator, node.left, node.right, resolvePath))
        }
    }

    private fun compare(
        operator: CompareOp,
        leftNode: Node,
        rightNode: Node,
        resolvePath: (String) -> RuntimeValue,
    ): Boolean {
        val left = evaluateNode(leftNode, resolvePath)
        val right = evaluateNode(rightNode, resolvePath)

        return when (operator) {
            CompareOp.EQ -> equalsValue(left, right)
            CompareOp.NE -> !equalsValue(left, right)
            CompareOp.GT,
            CompareOp.GE,
            CompareOp.LT,
            CompareOp.LE, -> {
                val leftNum = asNumber(left)
                val rightNum = asNumber(right)
                when (operator) {
                    CompareOp.GT -> leftNum > rightNum
                    CompareOp.GE -> leftNum >= rightNum
                    CompareOp.LT -> leftNum < rightNum
                    CompareOp.LE -> leftNum <= rightNum
                    else -> false
                }
            }
        }
    }

    private fun equalsValue(left: RuntimeValue, right: RuntimeValue): Boolean {
        if (left is RuntimeValue.Null || right is RuntimeValue.Null) {
            return left is RuntimeValue.Null && right is RuntimeValue.Null
        }

        if (left is RuntimeValue.Bool && right is RuntimeValue.Bool) {
            return left.value == right.value
        }

        if (left is RuntimeValue.Number && right is RuntimeValue.Number) {
            return left.value == right.value
        }

        if (left is RuntimeValue.Text && right is RuntimeValue.Text) {
            return left.value == right.value
        }

        if (left is RuntimeValue.Object || right is RuntimeValue.Object) {
            throw ConditionEvaluationException(
                "ERR_CONDITION_TYPE: '==' supports null, booleans, numbers, and strings only",
            )
        }

        throw ConditionEvaluationException(
            "ERR_CONDITION_TYPE: cannot compare ${describe(left)} and ${describe(right)}",
        )
    }

    private fun asNumber(value: RuntimeValue): Double {
        if (value is RuntimeValue.Number) {
            return value.value
        }
        throw ConditionEvaluationException(
            "ERR_CONDITION_TYPE: numeric comparison requires numbers (got ${describe(value)})",
        )
    }

    private fun describe(value: RuntimeValue): String {
        return when (value) {
            RuntimeValue.Null -> "null"
            is RuntimeValue.Bool -> "boolean"
            is RuntimeValue.Number -> "number"
            is RuntimeValue.Text -> "string"
            is RuntimeValue.Object -> "object"
        }
    }

    private fun isTruthy(value: RuntimeValue): Boolean {
        return when (value) {
            RuntimeValue.Null -> false
            is RuntimeValue.Bool -> value.value
            is RuntimeValue.Number -> value.value != 0.0
            is RuntimeValue.Text -> true
            is RuntimeValue.Object -> true
        }
    }

    private sealed interface Node {
        data class Path(val path: String) : Node

        data class Literal(val value: RuntimeValue) : Node

        data class Not(val expr: Node) : Node

        data class And(val left: Node, val right: Node) : Node

        data class Or(val left: Node, val right: Node) : Node

        data class Compare(val operator: CompareOp, val left: Node, val right: Node) : Node
    }

    private enum class CompareOp(val symbol: String) {
        EQ("=="),
        NE("!="),
        GT(">"),
        GE(">="),
        LT("<"),
        LE("<="),
    }

    private class Parser(private val expression: String) {
        private val tokens = tokenize(expression)
        private var index = 0

        fun parseExpression(): Node = parseOr()

        fun expectEnd() {
            expect(TokenType.EOF, "Unexpected trailing input")
        }

        fun expect(type: TokenType, message: String): Token {
            val token = current()
            if (token.type != type) {
                throw syntaxError(message, token)
            }
            index += 1
            return token
        }

        private fun parseOr(): Node {
            var left = parseAnd()
            while (match(TokenType.OR)) {
                left = Node.Or(left, parseAnd())
            }
            return left
        }

        private fun parseAnd(): Node {
            var left = parseUnary()
            while (match(TokenType.AND)) {
                left = Node.And(left, parseUnary())
            }
            return left
        }

        private fun parseUnary(): Node {
            return if (match(TokenType.NOT)) {
                Node.Not(parseUnary())
            } else {
                parseComparison()
            }
        }

        private fun parseComparison(): Node {
            val left = parsePrimary()
            val token = current()
            val operator =
                when (token.type) {
                    TokenType.EQ -> CompareOp.EQ
                    TokenType.NE -> CompareOp.NE
                    TokenType.GT -> CompareOp.GT
                    TokenType.GE -> CompareOp.GE
                    TokenType.LT -> CompareOp.LT
                    TokenType.LE -> CompareOp.LE
                    else -> null
                }
            if (operator == null) {
                return left
            }
            index += 1
            val right = parsePrimary()
            return Node.Compare(operator, left, right)
        }

        private fun parsePrimary(): Node {
            val token = current()
            return when (token.type) {
                TokenType.LPAREN -> {
                    index += 1
                    val inner = parseExpression()
                    expect(TokenType.RPAREN, "Expected ')' after expression")
                    inner
                }
                TokenType.TRUE -> {
                    index += 1
                    Node.Literal(RuntimeValue.Bool(true))
                }
                TokenType.FALSE -> {
                    index += 1
                    Node.Literal(RuntimeValue.Bool(false))
                }
                TokenType.NULL -> {
                    index += 1
                    Node.Literal(RuntimeValue.Null)
                }
                TokenType.NUMBER -> {
                    index += 1
                    val value =
                        token.text.toDoubleOrNull()
                            ?: throw syntaxError("Invalid numeric literal '${token.text}'", token)
                    Node.Literal(RuntimeValue.Number(value))
                }
                TokenType.STRING -> {
                    index += 1
                    Node.Literal(RuntimeValue.Text(token.text))
                }
                TokenType.IDENT -> parsePath()
                else -> throw syntaxError(
                    "Expected value, literal, or '(' but found ${renderToken(token)}",
                    token,
                )
            }
        }

        private fun parsePath(): Node {
            val first = expect(TokenType.IDENT, "Expected identifier").text
            val segments = mutableListOf(first)
            while (match(TokenType.DOT)) {
                segments += expect(TokenType.IDENT, "Expected identifier after '.'").text
            }
            return Node.Path(segments.joinToString("."))
        }

        private fun match(type: TokenType): Boolean {
            if (current().type != type) {
                return false
            }
            index += 1
            return true
        }

        private fun current(): Token = tokens[index]

        private fun syntaxError(message: String, token: Token): ConditionSyntaxException {
            val location =
                if (token.type == TokenType.EOF) {
                    "end of expression"
                } else {
                    "position ${token.start + 1}"
                }
            return ConditionSyntaxException("$message at $location")
        }

        private fun renderToken(token: Token): String {
            return if (token.type == TokenType.EOF) {
                "end of expression"
            } else {
                "'${token.raw}'"
            }
        }

        private data class Token(
            val type: TokenType,
            val text: String,
            val raw: String,
            val start: Int,
        )

        private enum class TokenType {
            LPAREN,
            RPAREN,
            DOT,
            NOT,
            AND,
            OR,
            EQ,
            NE,
            GT,
            GE,
            LT,
            LE,
            TRUE,
            FALSE,
            NULL,
            NUMBER,
            STRING,
            IDENT,
            EOF,
        }

        companion object {
            private fun tokenize(source: String): List<Token> {
                val tokens = mutableListOf<Token>()
                var i = 0
                while (i < source.length) {
                    val ch = source[i]
                    when {
                        ch.isWhitespace() -> i += 1
                        ch == '(' -> {
                            tokens += Token(TokenType.LPAREN, "(", "(", i)
                            i += 1
                        }
                        ch == ')' -> {
                            tokens += Token(TokenType.RPAREN, ")", ")", i)
                            i += 1
                        }
                        ch == '.' -> {
                            tokens += Token(TokenType.DOT, ".", ".", i)
                            i += 1
                        }
                        ch == '!' && source.getOrNull(i + 1) == '=' -> {
                            tokens += Token(TokenType.NE, "!=", "!=", i)
                            i += 2
                        }
                        ch == '=' && source.getOrNull(i + 1) == '=' -> {
                            tokens += Token(TokenType.EQ, "==", "==", i)
                            i += 2
                        }
                        ch == '>' && source.getOrNull(i + 1) == '=' -> {
                            tokens += Token(TokenType.GE, ">=", ">=", i)
                            i += 2
                        }
                        ch == '<' && source.getOrNull(i + 1) == '=' -> {
                            tokens += Token(TokenType.LE, "<=", "<=", i)
                            i += 2
                        }
                        ch == '&' && source.getOrNull(i + 1) == '&' -> {
                            tokens += Token(TokenType.AND, "&&", "&&", i)
                            i += 2
                        }
                        ch == '|' && source.getOrNull(i + 1) == '|' -> {
                            tokens += Token(TokenType.OR, "||", "||", i)
                            i += 2
                        }
                        ch == '!' -> {
                            tokens += Token(TokenType.NOT, "!", "!", i)
                            i += 1
                        }
                        ch == '>' -> {
                            tokens += Token(TokenType.GT, ">", ">", i)
                            i += 1
                        }
                        ch == '<' -> {
                            tokens += Token(TokenType.LT, "<", "<", i)
                            i += 1
                        }
                        ch == '"' -> {
                            val start = i
                            i += 1
                            val builder = StringBuilder()
                            var closed = false
                            while (i < source.length) {
                                val cur = source[i]
                                if (cur == '"') {
                                    closed = true
                                    i += 1
                                    break
                                }
                                if (cur == '\\') {
                                    val next = source.getOrNull(i + 1)
                                        ?: throw ConditionSyntaxException(
                                            "Unterminated escape sequence at position ${i + 1}",
                                        )
                                    when (next) {
                                        '"' -> builder.append('"')
                                        '\\' -> builder.append('\\')
                                        'n' -> builder.append('\n')
                                        'r' -> builder.append('\r')
                                        't' -> builder.append('\t')
                                        else -> throw ConditionSyntaxException(
                                            "Unsupported escape \\${next} at position ${i + 1}",
                                        )
                                    }
                                    i += 2
                                    continue
                                }
                                builder.append(cur)
                                i += 1
                            }
                            if (!closed) {
                                throw ConditionSyntaxException(
                                    "Unterminated string literal at position ${start + 1}",
                                )
                            }
                            val raw = source.substring(start, i)
                            tokens += Token(TokenType.STRING, builder.toString(), raw, start)
                        }
                        ch.isDigit() -> {
                            val start = i
                            while (source.getOrNull(i)?.isDigit() == true) {
                                i += 1
                            }
                            if (source.getOrNull(i) == '.' && source.getOrNull(i + 1)?.isDigit() == true) {
                                i += 1
                                while (source.getOrNull(i)?.isDigit() == true) {
                                    i += 1
                                }
                            }
                            val raw = source.substring(start, i)
                            tokens += Token(TokenType.NUMBER, raw, raw, start)
                        }
                        ch.isIdentifierStart() -> {
                            val start = i
                            i += 1
                            while (source.getOrNull(i)?.isIdentifierPart() == true) {
                                i += 1
                            }
                            val raw = source.substring(start, i)
                            val type =
                                when (raw) {
                                    "true" -> TokenType.TRUE
                                    "false" -> TokenType.FALSE
                                    "null" -> TokenType.NULL
                                    else -> TokenType.IDENT
                                }
                            tokens += Token(type, raw, raw, start)
                        }
                        else -> {
                            throw ConditionSyntaxException(
                                "Unsupported token '${source[i]}' at position ${i + 1}",
                            )
                        }
                    }
                }

                tokens += Token(TokenType.EOF, "", "", source.length)
                return tokens
            }

            private fun Char.isIdentifierStart(): Boolean {
                return this == '_' || this == '$' || this.isLetter()
            }

            private fun Char.isIdentifierPart(): Boolean {
                return this == '_' || this == '$' || this.isLetterOrDigit()
            }
        }
    }
}

internal class ConditionSyntaxException(message: String) : IllegalArgumentException(message)

internal class ConditionEvaluationException(message: String) : RuntimeException(message)
