plugins {
    kotlin("jvm") version "2.0.21"
    kotlin("plugin.serialization") version "2.0.21"
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "dev.androidemu"
version = "0.1.10"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.3")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.jar {
    manifest {
        attributes["Main-Class"] = "dev.androidemu.jdibridge.MainKt"
    }
}

tasks.shadowJar {
    archiveClassifier.set("all")
    manifest {
        attributes["Main-Class"] = "dev.androidemu.jdibridge.MainKt"
    }
}

tasks.test {
    useJUnitPlatform()
    jvmArgs("--add-modules", "jdk.jdi")
    // Prevent infinite hangs from JDI event loop tests
    systemProperty("junit.jupiter.execution.timeout.default", "30s")
}
