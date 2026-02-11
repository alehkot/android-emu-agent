package dev.androidemu.jdibridge

import com.sun.jdi.Bootstrap
import com.sun.jdi.VMDisconnectedException
import com.sun.jdi.VirtualMachine
import com.sun.jdi.connect.AttachingConnector
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Manages a single JDI connection to a target JVM.
 *
 * Thread safety: [status] may be called from any thread.
 * The event loop runs on its own daemon thread.
 */
class JdiSession(
    private val notificationEmitter: (JsonElement) -> Unit,
) {
    @Volatile
    private var vm: VirtualMachine? = null

    @Volatile
    private var eventThread: Thread? = null

    @Volatile
    private var disconnected = false

    @Volatile
    private var disconnectReason: String? = null

    val isAttached: Boolean get() = vm != null && !disconnected

    fun attach(host: String, port: Int): JsonElement {
        if (vm != null) {
            throw RpcException(INVALID_REQUEST, "Already attached to a VM; detach first")
        }

        val connector = findSocketAttachConnector()
        val args = connector.defaultArguments()
        args["hostname"]!!.setValue(host)
        args["port"]!!.setValue(port.toString())
        args["timeout"]!!.setValue("5000")

        log("attaching to $host:$port")
        val machine = try {
            connector.attach(args)
        } catch (e: Exception) {
            throw RpcException(INTERNAL_ERROR, "Failed to attach: ${e.message}")
        }

        vm = machine
        disconnected = false
        disconnectReason = null

        // If the VM is fully suspended (wait-for-debugger), resume it
        if (machine.allThreads().all { it.isSuspended }) {
            log("vm fully suspended, resuming")
            machine.resume()
        }

        startEventLoop(machine)

        return buildJsonObject {
            put("status", "attached")
            put("vm_name", machine.name())
            put("vm_version", machine.version())
            put("thread_count", machine.allThreads().size)
        }
    }

    fun detach(): JsonElement {
        val machine = vm ?: throw RpcException(INVALID_REQUEST, "Not attached to any VM")

        stopEventLoop()
        try {
            machine.dispose()
        } catch (_: Exception) {
            // VM may already be gone
        }
        vm = null
        disconnected = false
        disconnectReason = null

        return buildJsonObject {
            put("status", "detached")
        }
    }

    fun status(): JsonElement {
        val machine = vm
        if (machine == null) {
            return buildJsonObject {
                put("status", "not_attached")
            }
        }

        if (disconnected) {
            return buildJsonObject {
                put("status", "disconnected")
                put("reason", disconnectReason ?: "unknown")
            }
        }

        return try {
            buildJsonObject {
                put("status", "attached")
                put("vm_name", machine.name())
                put("vm_version", machine.version())
                put("thread_count", machine.allThreads().size)
            }
        } catch (e: Exception) {
            buildJsonObject {
                put("status", "disconnected")
                put("reason", e.message ?: "unknown")
            }
        }
    }

    private fun startEventLoop(machine: VirtualMachine) {
        // Use a polling watchdog approach: periodically probe the VM
        // instead of relying on EventQueue.remove() which can block
        // indefinitely when the target is killed on some platforms.
        val thread = Thread({
            try {
                while (!Thread.currentThread().isInterrupted) {
                    try {
                        // Probe VM liveness — throws VMDisconnectedException if dead
                        machine.allThreads()
                        Thread.sleep(500)
                    } catch (_: VMDisconnectedException) {
                        handleDisconnect("VM disconnected")
                        break
                    } catch (_: InterruptedException) {
                        break
                    } catch (e: Exception) {
                        // Other errors (e.g., transport closed) also mean disconnect
                        handleDisconnect("Event loop error: ${e.message}")
                        break
                    }
                }
            } catch (_: Exception) {
                // Outer catch for safety
            }
        }, "jdi-event-loop")
        thread.isDaemon = true
        thread.start()
        eventThread = thread
    }

    private fun stopEventLoop() {
        eventThread?.interrupt()
        eventThread?.join(2000)
        eventThread = null
    }

    private fun handleDisconnect(reason: String) {
        log("vm disconnected: $reason")
        disconnected = true
        disconnectReason = reason

        val notification = buildJsonObject {
            put("jsonrpc", "2.0")
            // No id = notification
            put("method", "vm_disconnected")
            put("params", buildJsonObject {
                put("reason", reason)
            })
        }
        try {
            notificationEmitter(notification)
        } catch (_: Exception) {
            // Best effort
        }
    }

    private fun findSocketAttachConnector(): AttachingConnector {
        val vmm = Bootstrap.virtualMachineManager()
        return vmm.attachingConnectors().firstOrNull {
            it.name() == "com.sun.jdi.SocketAttach"
        } ?: throw RpcException(INTERNAL_ERROR, "SocketAttach connector not found in JDK")
    }
}
