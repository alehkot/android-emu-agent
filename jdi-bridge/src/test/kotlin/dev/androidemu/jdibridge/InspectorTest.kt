package dev.androidemu.jdibridge

import com.sun.jdi.ArrayReference
import com.sun.jdi.ArrayType
import com.sun.jdi.Value
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.lang.reflect.Proxy

class InspectorTest {
    @Test
    fun `array preview uses a bounded JDWP range read`() {
        val requestedRanges = mutableListOf<Pair<Int, Int>>()
        val arrayType = proxy<ArrayType> { method, _ ->
            when (method.name) {
                "name" -> "int[]"
                else -> defaultValue(method.returnType)
            }
        }
        val array = proxy<ArrayReference> { method, args ->
            when (method.name) {
                "length" -> 1_000_000
                "uniqueID" -> 7L
                "referenceType", "type" -> arrayType
                "getValues" -> {
                    require(args?.size == 2) { "Inspector requested the entire remote array" }
                    val start = args[0] as Int
                    val length = args[1] as Int
                    requestedRanges.add(start to length)
                    List<Value?>(length) { null }
                }
                else -> defaultValue(method.returnType)
            }
        }

        val result = Inspector(maxCollectionItems = 10).inspectValue(array, depth = 1)
        val value = result["value"]!!.jsonObject

        assertEquals(listOf(0 to 10), requestedRanges)
        assertEquals(1_000_000, value["length"]?.jsonPrimitive?.int)
        assertEquals(10, value["items"]?.jsonArray?.size)
        assertTrue(result["truncated"]!!.jsonPrimitive.boolean)
    }

    private inline fun <reified T> proxy(
        crossinline handler: (java.lang.reflect.Method, Array<out Any?>?) -> Any?,
    ): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, method, args ->
            handler(method, args)
        } as T

    private fun defaultValue(returnType: Class<*>): Any? =
        when (returnType) {
            Boolean::class.javaPrimitiveType -> false
            Byte::class.javaPrimitiveType -> 0.toByte()
            Short::class.javaPrimitiveType -> 0.toShort()
            Int::class.javaPrimitiveType -> 0
            Long::class.javaPrimitiveType -> 0L
            Float::class.javaPrimitiveType -> 0F
            Double::class.javaPrimitiveType -> 0.0
            Char::class.javaPrimitiveType -> '\u0000'
            else -> null
        }
}
