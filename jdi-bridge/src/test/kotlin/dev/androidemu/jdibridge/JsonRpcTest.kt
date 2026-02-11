package dev.androidemu.jdibridge

import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class JsonRpcTest {

    @Test
    fun `parseRequest with valid ping request`() {
        val line = """{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}"""
        val req = parseRequest(line)
        assertEquals(1, req.id)
        assertEquals("ping", req.method)
    }

    @Test
    fun `parseRequest with missing params defaults to empty object`() {
        val line = """{"jsonrpc": "2.0", "id": 2, "method": "status"}"""
        val req = parseRequest(line)
        assertEquals("status", req.method)
        assertTrue(req.params.isEmpty())
    }

    @Test
    fun `parseRequest with null id`() {
        val line = """{"jsonrpc": "2.0", "id": null, "method": "ping"}"""
        val req = parseRequest(line)
        assertNull(req.id)
        assertEquals("ping", req.method)
    }

    @Test
    fun `parseRequest rejects missing jsonrpc version`() {
        val line = """{"id": 1, "method": "ping"}"""
        val ex = assertThrows<RpcException> { parseRequest(line) }
        assertEquals(INVALID_REQUEST, ex.code)
    }

    @Test
    fun `parseRequest rejects wrong jsonrpc version`() {
        val line = """{"jsonrpc": "1.0", "id": 1, "method": "ping"}"""
        val ex = assertThrows<RpcException> { parseRequest(line) }
        assertEquals(INVALID_REQUEST, ex.code)
    }

    @Test
    fun `parseRequest rejects missing method`() {
        val line = """{"jsonrpc": "2.0", "id": 1}"""
        val ex = assertThrows<RpcException> { parseRequest(line) }
        assertEquals(INVALID_REQUEST, ex.code)
    }

    @Test
    fun `successResponse formats correctly`() {
        val result = json.parseToJsonElement("""{"pong": true}""")
        val response = successResponse(1, result)
        val parsed = json.parseToJsonElement(response).jsonObject

        assertEquals("2.0", parsed["jsonrpc"]?.jsonPrimitive?.content)
        assertEquals(1, parsed["id"]?.jsonPrimitive?.int)
        assertTrue(parsed["result"]!!.jsonObject["pong"]!!.jsonPrimitive.boolean)
        assertTrue(parsed["error"] == null || parsed["error"] is JsonNull)
    }

    @Test
    fun `errorResponse formats correctly`() {
        val response = errorResponse(5, METHOD_NOT_FOUND, "Unknown method: foo")
        val parsed = json.parseToJsonElement(response).jsonObject

        assertEquals("2.0", parsed["jsonrpc"]?.jsonPrimitive?.content)
        assertEquals(5, parsed["id"]?.jsonPrimitive?.int)
        assertTrue(parsed["result"] == null || parsed["result"] is JsonNull)
        val error = parsed["error"]!!.jsonObject
        assertEquals(-32601, error["code"]?.jsonPrimitive?.int)
        assertEquals("Unknown method: foo", error["message"]?.jsonPrimitive?.content)
    }

    @Test
    fun `errorResponse with null id`() {
        val response = errorResponse(null, PARSE_ERROR, "bad json")
        val parsed = json.parseToJsonElement(response).jsonObject
        // id should be null in the JSON
        assertTrue(parsed["id"] is kotlinx.serialization.json.JsonNull)
    }

    @Test
    fun `handleLine dispatches ping`() {
        val line = """{"jsonrpc": "2.0", "id": 1, "method": "ping"}"""
        val response = handleLine(line)
        assertNotNull(response)
        val parsed = json.parseToJsonElement(response).jsonObject
        assertTrue(parsed["result"]!!.jsonObject["pong"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `handleLine returns method not found for unknown method`() {
        val line = """{"jsonrpc": "2.0", "id": 1, "method": "nonexistent"}"""
        val response = handleLine(line)
        assertNotNull(response)
        val parsed = json.parseToJsonElement(response).jsonObject
        val error = parsed["error"]!!.jsonObject
        assertEquals(-32601, error["code"]?.jsonPrimitive?.content?.toInt())
    }

    @Test
    fun `handleLine returns parse error for invalid JSON`() {
        val response = handleLine("not json at all")
        assertNotNull(response)
        val parsed = json.parseToJsonElement(response).jsonObject
        val error = parsed["error"]!!.jsonObject
        assertEquals(-32700, error["code"]?.jsonPrimitive?.content?.toInt())
    }
}
