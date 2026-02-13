package dev.androidemu.jdibridge

import java.nio.file.Files
import java.nio.file.Path

/**
 * Lightweight ProGuard/R8 mapping parser used for debugger deobfuscation.
 *
 * Supports class, field, and method name mapping. Method overloads are disambiguated
 * by argument count when available.
 */
class ProguardMapping private constructor(
    classMappings: List<ClassMapping>,
) {
    private data class MethodMapping(
        val originalName: String,
        val obfuscatedName: String,
        val arity: Int,
    )

    private data class ClassMapping(
        val originalName: String,
        val obfuscatedName: String,
        val fieldsByObfuscated: Map<String, String>,
        val fieldsByOriginal: Map<String, String>,
        val methodsByObfuscated: Map<String, List<MethodMapping>>,
    )

    private data class ClassMappingBuilder(
        val originalName: String,
        val obfuscatedName: String,
        val fieldsByObfuscated: MutableMap<String, String> = linkedMapOf(),
        val fieldsByOriginal: MutableMap<String, String> = linkedMapOf(),
        val methodsByObfuscated: MutableMap<String, MutableList<MethodMapping>> = linkedMapOf(),
    ) {
        fun build(): ClassMapping {
            return ClassMapping(
                originalName = originalName,
                obfuscatedName = obfuscatedName,
                fieldsByObfuscated = fieldsByObfuscated.toMap(),
                fieldsByOriginal = fieldsByOriginal.toMap(),
                methodsByObfuscated = methodsByObfuscated.mapValues { (_, value) -> value.toList() },
            )
        }
    }

    companion object {
        private val CLASS_PATTERN = Regex("^(.+)\\s+->\\s+(.+):$")

        fun load(pathText: String): ProguardMapping {
            if (pathText.isBlank()) {
                throw RpcException(INVALID_PARAMS, "path must not be blank")
            }

            val path = Path.of(pathText)
            if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
                throw RpcException(INVALID_PARAMS, "Mapping file not readable: $pathText")
            }

            val lines = try {
                Files.readAllLines(path)
            } catch (e: Exception) {
                throw RpcException(INVALID_PARAMS, "Failed to read mapping file: ${e.message}")
            }
            return parseLines(lines)
        }

        internal fun parse(content: String): ProguardMapping {
            return parseLines(content.lines())
        }

        private fun parseLines(lines: List<String>): ProguardMapping {
            val classes = mutableListOf<ClassMapping>()
            var current: ClassMappingBuilder? = null

            for (line in lines) {
                val trimmed = line.trim()
                if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                    continue
                }

                val classMatch = CLASS_PATTERN.matchEntire(trimmed)
                if (classMatch != null) {
                    current?.let { classes.add(it.build()) }
                    current = ClassMappingBuilder(
                        originalName = classMatch.groupValues[1].trim(),
                        obfuscatedName = classMatch.groupValues[2].trim(),
                    )
                    continue
                }

                if (line.startsWith(" ") || line.startsWith("\t")) {
                    current?.let { parseMemberLine(trimmed, it) }
                }
            }

            current?.let { classes.add(it.build()) }
            return ProguardMapping(classes)
        }

        private fun parseMemberLine(line: String, builder: ClassMappingBuilder) {
            val parts = line.split("->", limit = 2)
            if (parts.size != 2) {
                return
            }

            val left = parts[0].trim()
            val obfuscatedName = parts[1].trim()
            if (left.isEmpty() || obfuscatedName.isEmpty()) {
                return
            }

            if (left.contains("(") && left.contains(")")) {
                parseMethod(left, obfuscatedName, builder)
            } else {
                parseField(left, obfuscatedName, builder)
            }
        }

        private fun parseField(
            left: String,
            obfuscatedName: String,
            builder: ClassMappingBuilder,
        ) {
            val originalName = left.substringAfterLast(' ').substringAfterLast(':').trim()
            if (originalName.isEmpty()) {
                return
            }
            builder.fieldsByObfuscated[obfuscatedName] = originalName
            builder.fieldsByOriginal[originalName] = obfuscatedName
        }

        private fun parseMethod(
            left: String,
            obfuscatedName: String,
            builder: ClassMappingBuilder,
        ) {
            val openParen = left.indexOf('(')
            val closeParen = left.indexOf(')', startIndex = openParen + 1)
            if (openParen <= 0 || closeParen <= openParen) {
                return
            }

            val methodToken = left.substring(0, openParen).trim()
            val originalName = methodToken.substringAfterLast(' ').substringAfterLast(':').trim()
            if (originalName.isEmpty()) {
                return
            }

            val argsText = left.substring(openParen + 1, closeParen).trim()
            val arity = if (argsText.isEmpty()) {
                0
            } else {
                argsText.split(",").size
            }

            val methods = builder.methodsByObfuscated.getOrPut(obfuscatedName) { mutableListOf() }
            methods.add(
                MethodMapping(
                    originalName = originalName,
                    obfuscatedName = obfuscatedName,
                    arity = arity,
                ),
            )
        }
    }

    private val classesByObfuscated: Map<String, ClassMapping> = classMappings.associateBy {
        it.obfuscatedName
    }
    private val classesByOriginal: Map<String, ClassMapping> = classMappings.associateBy {
        it.originalName
    }

    val classCount: Int
        get() = classesByObfuscated.size

    val memberCount: Int
        get() = classesByObfuscated.values.sumOf { classMapping ->
            classMapping.fieldsByObfuscated.size + classMapping.methodsByObfuscated.values.sumOf {
                it.size
            }
        }

    fun deobfuscateClass(className: String): String {
        return classesByObfuscated[className]?.originalName ?: className
    }

    fun deobfuscateTypeName(typeName: String): String {
        if (typeName.isBlank()) {
            return typeName
        }

        var base = typeName
        var arraySuffix = ""
        while (base.endsWith("[]")) {
            base = base.removeSuffix("[]")
            arraySuffix += "[]"
        }

        if (base in PRIMITIVE_TYPES) {
            return base + arraySuffix
        }

        return deobfuscateClass(base) + arraySuffix
    }

    fun deobfuscateMethod(
        className: String,
        methodName: String,
        arity: Int? = null,
    ): String {
        val classMapping = classesByObfuscated[className] ?: return methodName
        val candidates = classMapping.methodsByObfuscated[methodName] ?: return methodName

        if (arity != null) {
            val exact = candidates.filter { it.arity == arity }
            if (exact.size == 1) {
                return exact[0].originalName
            }
        }

        return candidates.firstOrNull()?.originalName ?: methodName
    }

    fun deobfuscateField(className: String, fieldName: String): String {
        val classMapping = classesByObfuscated[className] ?: return fieldName
        return classMapping.fieldsByObfuscated[fieldName] ?: fieldName
    }

    fun obfuscateField(className: String, originalFieldName: String): String? {
        val classMapping = classesByObfuscated[className]
            ?: classesByOriginal[className]
            ?: return null
        return classMapping.fieldsByOriginal[originalFieldName]
    }
}

private val PRIMITIVE_TYPES = setOf(
    "boolean",
    "byte",
    "char",
    "short",
    "int",
    "long",
    "float",
    "double",
    "void",
)
