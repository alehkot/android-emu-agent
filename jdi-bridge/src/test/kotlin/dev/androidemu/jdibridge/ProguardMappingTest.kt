package dev.androidemu.jdibridge

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class ProguardMappingTest {

    @Test
    fun `parses class field and method mappings`() {
        val mapping = ProguardMapping.parse(
            """
            com.example.UserService -> a.b.c:
                int profileId -> b
                java.lang.String fetchProfile(java.lang.String) -> a
            """.trimIndent(),
        )

        assertEquals(1, mapping.classCount)
        assertEquals(2, mapping.memberCount)
        assertEquals("com.example.UserService", mapping.deobfuscateClass("a.b.c"))
        assertEquals("fetchProfile", mapping.deobfuscateMethod("a.b.c", "a", arity = 1))
        assertEquals("profileId", mapping.deobfuscateField("a.b.c", "b"))
        assertEquals("b", mapping.obfuscateField("a.b.c", "profileId"))
        assertEquals("com.example.UserService[]", mapping.deobfuscateTypeName("a.b.c[]"))
        assertNull(mapping.obfuscateField("a.b.c", "unknown"))
    }
}
