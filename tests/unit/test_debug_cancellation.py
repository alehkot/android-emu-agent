"""Cancellation must release resources acquired by unfinished debugger operations."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.debugger.manager import DebugManager, DebugSessionState
from android_emu_agent.errors import AgentError


def _bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.is_alive = True
    bridge.start = AsyncMock()
    bridge.ping = AsyncMock(return_value={"status": "ok"})
    bridge.request = AsyncMock()
    bridge.stop = AsyncMock()
    return bridge


def _port_socket(port: int = 54321) -> MagicMock:
    port_socket = MagicMock()
    port_socket.__enter__.return_value = port_socket
    port_socket.getsockname.return_value = ("127.0.0.1", port)
    return port_socket


def _assert_no_session(manager: DebugManager) -> None:
    assert not manager._bridges
    assert not manager._debug_sessions
    assert not manager._adb_devices
    assert not manager._event_tasks
    assert not manager._event_queues
    assert not manager._logpoint_histories


async def _run_operation(manager: DebugManager, operation: str, adb_device: MagicMock) -> None:
    if operation == "start":
        await manager.start_bridge("s-test")
    elif operation == "ping":
        await manager.ping("s-test")
    else:
        await manager.attach("s-test", "emulator-5554", "com.example.app", adb_device)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["start", "ping"])
async def test_start_bridge_cancellation_stops_unregistered_client(stage: str) -> None:
    manager = DebugManager()
    bridge = _bridge()
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def blocked() -> dict[str, str]:
        entered.set()
        await release.wait()
        finished.set()
        return {"status": "ok"}

    getattr(bridge, stage).side_effect = blocked
    with (
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=bridge),
    ):
        task = asyncio.create_task(manager.start_bridge("s-test"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel("cancel startup")
        release.set()
        with pytest.raises(asyncio.CancelledError, match="cancel startup"):
            await asyncio.wait_for(task, timeout=2)

    bridge.stop.assert_awaited_once_with()
    if stage == "start":
        assert finished.is_set(), "Settle subprocess creation before stopping its client"
        bridge.ping.assert_not_awaited()
    _assert_no_session(manager)


@pytest.mark.asyncio
async def test_attach_cancellation_cleans_forward_and_registered_bridge() -> None:
    manager = DebugManager()
    bridge = _bridge()
    adb_device = MagicMock()
    entered = asyncio.Event()

    async def request(*_args: object, **_kwargs: object) -> None:
        entered.set()
        await asyncio.Future[None]()

    bridge.request.side_effect = request
    manager._bridges["s-test"] = bridge
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
    ):
        task = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", adb_device)
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel("cancel attach")
        with pytest.raises(asyncio.CancelledError, match="cancel attach"):
            await asyncio.wait_for(task, timeout=2)

    adb_device.forward_remove.assert_called_once_with("tcp:54321", False)
    bridge.stop.assert_awaited_once_with()
    _assert_no_session(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("allocation_fails", [False, True])
@pytest.mark.parametrize("cancel_twice", [False, True])
async def test_forward_allocation_cancellation_settles_thread(
    allocation_fails: bool, cancel_twice: bool
) -> None:
    manager = DebugManager()
    adb_device = MagicMock()
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    finished = asyncio.Event()
    release = threading.Event()

    def forward(_local: str, _remote: str, *, norebind: bool) -> None:
        assert norebind
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(timeout=2), "Test must release the worker thread"
            if allocation_fails:
                raise RuntimeError("allocation failed after cancellation")
        finally:
            loop.call_soon_threadsafe(finished.set)

    adb_device.forward.side_effect = forward
    with patch("android_emu_agent.debugger.manager.socket.socket", return_value=_port_socket()):
        task = asyncio.create_task(manager._setup_forward(123, adb_device))
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel("cancel forwarding")
            if cancel_twice:
                await asyncio.sleep(0)
                task.cancel("second cancellation")
            release.set()
            with pytest.raises(asyncio.CancelledError, match="cancel forwarding"):
                await asyncio.wait_for(task, timeout=2)
            await asyncio.wait_for(finished.wait(), timeout=2)
        finally:
            release.set()

    if allocation_fails:
        adb_device.forward_remove.assert_not_called()
    else:
        adb_device.forward_remove.assert_called_once_with("tcp:54321", False)
    _assert_no_session(manager)


@pytest.mark.asyncio
async def test_cancelled_attach_waiting_for_start_lock_keeps_unacquired_bridge() -> None:
    manager = DebugManager()
    bridge = _bridge()
    manager._bridges["s-test"] = bridge
    adb_device = MagicMock()
    forwarded = asyncio.Event()

    async def setup(_pid: int, _device: object) -> int:
        forwarded.set()
        return 54321

    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", side_effect=setup),
    ):
        async with manager._bridge_start_lock:
            task = asyncio.create_task(
                manager.attach("s-test", "emulator-5554", "com.example.app", adb_device)
            )
            await asyncio.wait_for(forwarded.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)

    adb_device.forward_remove.assert_called_once_with("tcp:54321", False)
    bridge.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": bridge}
    assert not manager._debug_sessions


@pytest.mark.asyncio
async def test_repeated_attach_cancellation_does_not_interrupt_cleanup() -> None:
    manager = DebugManager()
    bridge = _bridge()
    manager._bridges["s-test"] = bridge
    request_entered = asyncio.Event()
    cleanup_entered = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def request(*_args: object, **_kwargs: object) -> None:
        request_entered.set()
        await asyncio.Future[None]()

    async def remove_forward(_port: int, _device: object) -> None:
        cleanup_entered.set()
        await release_cleanup.wait()
        cleanup_finished.set()

    bridge.request.side_effect = request
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
        patch.object(manager, "_remove_forward", side_effect=remove_forward),
    ):
        task = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(request_entered.wait(), timeout=2)
        task.cancel("original cancellation")
        try:
            await asyncio.wait_for(cleanup_entered.wait(), timeout=2)
            task.cancel("second cancellation")
        finally:
            release_cleanup.set()
            with pytest.raises(asyncio.CancelledError, match="original cancellation"):
                await asyncio.wait_for(task, timeout=2)

    assert cleanup_finished.is_set()
    bridge.stop.assert_awaited_once_with()
    _assert_no_session(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "attach", "ping"])
async def test_cleanup_failure_does_not_replace_cancellation(operation: str) -> None:
    manager = DebugManager()
    bridge = _bridge()
    adb_device = MagicMock()
    entered = asyncio.Event()

    async def blocked(*_args: object, **_kwargs: object) -> None:
        entered.set()
        await asyncio.Future[None]()

    bridge.ping.side_effect = blocked
    bridge.request.side_effect = blocked
    bridge.stop.side_effect = RuntimeError("shutdown failed")
    with (
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=bridge),
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
    ):
        if operation != "start":
            manager._bridges["s-test"] = bridge
        task = asyncio.create_task(_run_operation(manager, operation, adb_device))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel("original cancellation")
        with pytest.raises(asyncio.CancelledError, match="original cancellation"):
            await asyncio.wait_for(task, timeout=2)

    bridge.stop.assert_awaited_once_with()
    if operation == "attach":
        adb_device.forward_remove.assert_called_once_with("tcp:54321", False)
    _assert_no_session(manager)


@pytest.mark.asyncio
async def test_cancelled_attach_keeps_replacement_bridge_registered() -> None:
    manager = DebugManager()
    bridge = _bridge()
    replacement = _bridge()
    manager._bridges["s-test"] = bridge
    entered = asyncio.Event()

    async def request(*_args: object, **_kwargs: object) -> None:
        entered.set()
        await asyncio.Future[None]()

    bridge.request.side_effect = request
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
    ):
        task = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        manager._bridges["s-test"] = replacement
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)

    bridge.stop.assert_awaited_once_with()
    replacement.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": replacement}
    assert not manager._debug_sessions


@pytest.mark.asyncio
async def test_cancelled_ping_keeps_established_debug_session() -> None:
    manager = DebugManager()
    bridge = _bridge()
    manager._bridges["s-test"] = bridge
    session = DebugSessionState(
        session_id="s-test",
        package="com.example.app",
        process_name="com.example.app",
        pid=123,
        jdwp_port=123,
        local_forward_port=54321,
        device_serial="emulator-5554",
    )
    manager._debug_sessions["s-test"] = session
    entered = asyncio.Event()

    async def ping() -> None:
        entered.set()
        await asyncio.Future[None]()

    bridge.ping.side_effect = ping
    task = asyncio.create_task(manager.ping("s-test"))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)

    bridge.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": bridge}
    assert manager._debug_sessions == {"s-test": session}


@pytest.mark.asyncio
async def test_transient_ping_retires_bridge_before_concurrent_attach() -> None:
    """A scheduled ping cleanup must not stop an attach's newly acquired bridge."""
    manager = DebugManager()
    bridge = _bridge()
    bridge.request.return_value = {"status": "attached"}
    replacement = _bridge()
    replacement.request.return_value = {"status": "attached"}
    manager._bridges["s-test"] = bridge
    forwarding = asyncio.Event()
    release_forward = asyncio.Event()

    async def setup(_pid: int, _device: object) -> int:
        forwarding.set()
        await release_forward.wait()
        return 54321

    async def ping() -> dict[str, bool]:
        # Queue the attaching caller before ping queues its cleanup task.
        release_forward.set()
        return {"pong": True}

    bridge.ping.side_effect = ping
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", side_effect=setup),
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch.object(manager, "_monitor_events", AsyncMock()),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=replacement),
    ):
        attach = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(forwarding.wait(), timeout=2)
        assert await manager.ping("s-test") == {"pong": True}
        result = await asyncio.wait_for(attach, timeout=2)
        await asyncio.gather(*manager._event_tasks.values())

    assert result["status"] == "attached"
    bridge.stop.assert_awaited_once_with()
    bridge.request.assert_not_awaited()
    replacement.start.assert_awaited_once_with()
    replacement.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": replacement}
    assert manager._debug_sessions["s-test"].state == "attached"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_waiter", [False, True])
async def test_concurrent_attach_waiter_preserves_successful_attachment(
    cancel_waiter: bool,
) -> None:
    """A queued attach must not borrow or roll back an attachment that just committed."""
    manager = DebugManager()
    bridge = _bridge()
    manager._bridges["s-test"] = bridge
    entered = asyncio.Event()
    release = asyncio.Event()
    loop = asyncio.get_running_loop()
    waiter: asyncio.Task[dict[str, object]] | None = None

    async def request(_method: str, params: dict[str, object]) -> dict[str, str]:
        if params["port"] == 54321:
            entered.set()
            await release.wait()
            if cancel_waiter:
                assert waiter is not None
                # The first attach commits before this cancellation is delivered.
                loop.call_soon(waiter.cancel, "cancel queued attach")
            return {"status": "attached"}
        await asyncio.Future[None]()
        raise AssertionError("Concurrent attach must not reach the bridge")

    bridge.request.side_effect = request
    with (
        patch.object(
            manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))
        ) as find_pid,
        patch.object(manager, "_setup_forward", AsyncMock(side_effect=[54321, 54322])) as setup,
        patch.object(manager, "_monitor_events", AsyncMock()),
    ):
        first = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        waiter = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.sleep(0)
        release.set()
        result = await asyncio.wait_for(first, timeout=2)
        if cancel_waiter:
            with pytest.raises(asyncio.CancelledError, match="cancel queued attach"):
                await asyncio.wait_for(waiter, timeout=2)
        else:
            with pytest.raises(AgentError) as exc_info:
                await asyncio.wait_for(waiter, timeout=2)
            assert exc_info.value.code == "ERR_ALREADY_ATTACHED"
        await asyncio.gather(*manager._event_tasks.values())

    assert result["status"] == "attached"
    bridge.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": bridge}
    assert manager._debug_sessions["s-test"].state == "attached"
    find_pid.assert_awaited_once()
    setup.assert_awaited_once()
    bridge.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_locks_do_not_serialize_different_sessions_or_retain_finished_locks() -> None:
    manager = DebugManager()
    first_bridge = _bridge()
    second_bridge = _bridge()
    manager._bridges = {"s-first": first_bridge, "s-second": second_bridge}
    entered = 0
    both_entered = asyncio.Event()
    release = asyncio.Event()

    async def request(_method: str, _params: dict[str, object]) -> dict[str, str]:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await release.wait()
        return {"status": "attached"}

    first_bridge.request.side_effect = request
    second_bridge.request.side_effect = request
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(side_effect=[54321, 54322])),
        patch.object(manager, "_monitor_events", AsyncMock()),
    ):
        tasks = [
            asyncio.create_task(
                manager.attach(session_id, "emulator-5554", "com.example.app", MagicMock())
            )
            for session_id in ("s-first", "s-second")
        ]
        try:
            await asyncio.wait_for(both_entered.wait(), timeout=2)
            assert len(manager._attach_locks) == 2
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
        await asyncio.gather(*manager._event_tasks.values())

    assert [result["session_id"] for result in results] == ["s-first", "s-second"]
    assert not manager._attach_locks
    first_bridge.stop.assert_not_awaited()
    second_bridge.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_attach_starts_after_cancelled_predecessor_finishes_rollback() -> None:
    manager = DebugManager()
    bridge = _bridge()
    replacement = _bridge()
    replacement.request.return_value = {"status": "attached"}
    manager._bridges["s-test"] = bridge
    entered = asyncio.Event()
    removing = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def request(_method: str, _params: dict[str, object]) -> None:
        entered.set()
        await asyncio.Future[None]()

    async def remove_forward(_port: int, _device: object) -> None:
        removing.set()
        await release_cleanup.wait()

    bridge.request.side_effect = request
    with (
        patch.object(
            manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))
        ) as find_pid,
        patch.object(manager, "_setup_forward", AsyncMock(side_effect=[54321, 54322])),
        patch.object(manager, "_remove_forward", side_effect=remove_forward),
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch.object(manager, "_monitor_events", AsyncMock()),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=replacement),
    ):
        first = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        first.cancel("cancel first attach")
        await asyncio.wait_for(removing.wait(), timeout=2)
        waiter = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.sleep(0)
        try:
            find_pid.assert_awaited_once()
        finally:
            release_cleanup.set()
        with pytest.raises(asyncio.CancelledError, match="cancel first attach"):
            await asyncio.wait_for(first, timeout=2)
        result = await asyncio.wait_for(waiter, timeout=2)
        await asyncio.gather(*manager._event_tasks.values())

    assert result["status"] == "attached"
    assert result["local_port"] == 54322
    bridge.stop.assert_awaited_once_with()
    replacement.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": replacement}


@pytest.mark.asyncio
async def test_forward_failure_keeps_actionable_error() -> None:
    manager = DebugManager()
    adb_device = MagicMock()
    adb_device.forward.side_effect = RuntimeError("device offline")
    with (
        patch("android_emu_agent.debugger.manager.socket.socket", return_value=_port_socket()),
        pytest.raises(AgentError) as exc_info,
    ):
        await manager._setup_forward(123, adb_device)

    assert exc_info.value.code == "ERR_ADB_FORWARD_FAILED"
    adb_device.forward_remove.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("port_collision", [False, True])
async def test_cancelled_forward_preserves_preexisting_rules(port_collision: bool) -> None:
    """Rollback may remove its private rule, never a reused or colliding rule."""
    manager = DebugManager()
    adb_device = MagicMock()
    rules = {"tcp:12345": "jdwp:123"}
    if port_collision:
        rules["tcp:54321"] = "jdwp:456"
    original_rules = dict(rules)
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()

    def forward(local: str, remote: str, *, norebind: bool) -> None:
        assert norebind
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=2), "Test must release the worker thread"
        if local in rules:
            raise RuntimeError("cannot rebind existing forward")
        rules[local] = remote

    def remove(local: str, _raise_non_found: bool) -> None:
        rules.pop(local)

    adb_device.forward.side_effect = forward
    adb_device.forward_remove.side_effect = remove
    with patch("android_emu_agent.debugger.manager.socket.socket", return_value=_port_socket()):
        task = asyncio.create_task(manager._setup_forward(123, adb_device))
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel("cancel private allocation")
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError, match="cancel private allocation"):
            await asyncio.wait_for(task, timeout=2)

    assert rules == original_rules
    adb_device.forward.assert_called_once_with("tcp:54321", "jdwp:123", norebind=True)
    adb_device.forward_port.assert_not_called()
    if port_collision:
        adb_device.forward_remove.assert_not_called()
    else:
        adb_device.forward_remove.assert_called_once_with("tcp:54321", False)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "attach", "ping"])
async def test_cancellation_during_failure_cleanup_finishes_stopping_bridge(operation: str) -> None:
    manager = DebugManager()
    bridge = _bridge()
    cleanup_entered = asyncio.Event()
    release = asyncio.Event()
    stopped = asyncio.Event()

    async def stop() -> None:
        cleanup_entered.set()
        await release.wait()
        stopped.set()

    bridge.stop.side_effect = stop
    bridge.ping.side_effect = RuntimeError("ping failed")
    bridge.request.side_effect = RuntimeError("attach failed")
    with (
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=bridge),
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
    ):
        if operation != "start":
            manager._bridges["s-test"] = bridge
        task = asyncio.create_task(_run_operation(manager, operation, MagicMock()))
        await asyncio.wait_for(cleanup_entered.wait(), timeout=2)
        task.cancel("cancel during cleanup")
        release.set()
        with pytest.raises(asyncio.CancelledError, match="cancel during cleanup"):
            await asyncio.wait_for(task, timeout=2)

    assert stopped.is_set()
    _assert_no_session(manager)


@pytest.mark.asyncio
async def test_repeated_transient_ping_cancellation_finishes_owned_cleanup() -> None:
    manager = DebugManager()
    bridge = _bridge()
    replacement = _bridge()
    manager._bridges["s-test"] = bridge
    ping_entered = asyncio.Event()
    cleanup_entered = asyncio.Event()
    release = asyncio.Event()
    stopped = asyncio.Event()

    async def ping() -> None:
        ping_entered.set()
        await asyncio.Future[None]()

    async def stop() -> None:
        cleanup_entered.set()
        await release.wait()
        stopped.set()

    bridge.ping.side_effect = ping
    bridge.stop.side_effect = stop
    task = asyncio.create_task(manager.ping("s-test"))
    await asyncio.wait_for(ping_entered.wait(), timeout=2)
    manager._bridges["s-test"] = replacement
    task.cancel("original cancellation")
    try:
        await asyncio.wait_for(cleanup_entered.wait(), timeout=2)
        task.cancel("second cancellation")
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError, match="original cancellation"):
            await asyncio.wait_for(task, timeout=2)

    assert stopped.is_set()
    bridge.stop.assert_awaited_once_with()
    replacement.stop.assert_not_awaited()
    assert manager._bridges == {"s-test": replacement}
    assert not manager._debug_sessions


@pytest.mark.asyncio
async def test_cancelled_start_failure_still_stops_client_and_preserves_cancellation() -> None:
    manager = DebugManager()
    bridge = _bridge()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def start() -> None:
        entered.set()
        await release.wait()
        raise RuntimeError("spawn failed after cancellation")

    bridge.start.side_effect = start
    with (
        patch.object(manager, "_find_java", return_value=Path("java")),
        patch.object(manager, "_find_jar", return_value=Path("bridge.jar")),
        patch("android_emu_agent.debugger.manager.BridgeClient", return_value=bridge),
    ):
        task = asyncio.create_task(manager.start_bridge("s-test", verify=False))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel("original cancellation")
        await asyncio.sleep(0)
        task.cancel("second cancellation")
        release.set()
        with pytest.raises(asyncio.CancelledError, match="original cancellation"):
            await asyncio.wait_for(task, timeout=2)

    bridge.stop.assert_awaited_once_with()
    bridge.ping.assert_not_awaited()
    _assert_no_session(manager)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_fails", [False, True])
@pytest.mark.parametrize("cancel_twice", [False, True])
@pytest.mark.parametrize("rpc_error", [False, True])
async def test_attach_failure_rollback_preserves_cancellation_during_forward_removal(
    stop_fails: bool, cancel_twice: bool, rpc_error: bool
) -> None:
    manager = DebugManager()
    bridge = _bridge()
    manager._bridges["s-test"] = bridge
    removing = asyncio.Event()
    stopping = asyncio.Event()
    release_forward = asyncio.Event()
    release_stop = asyncio.Event()
    stopped = asyncio.Event()

    async def remove_forward(_port: int, _device: object) -> None:
        removing.set()
        await release_forward.wait()

    async def stop() -> None:
        stopping.set()
        await release_stop.wait()
        stopped.set()
        if stop_fails:
            raise RuntimeError("stop failed after cancellation")

    if rpc_error:
        bridge.request.return_value = {"error": {"message": "attach failed"}}
    else:
        bridge.request.side_effect = RuntimeError("attach failed")
    bridge.stop.side_effect = stop
    with (
        patch.object(manager, "_find_pid", AsyncMock(return_value=(123, "com.example.app"))),
        patch.object(manager, "_setup_forward", AsyncMock(return_value=54321)),
        patch.object(manager, "_remove_forward", side_effect=remove_forward) as remove,
    ):
        task = asyncio.create_task(
            manager.attach("s-test", "emulator-5554", "com.example.app", MagicMock())
        )
        await asyncio.wait_for(removing.wait(), timeout=2)
        task.cancel("original cancellation")
        release_forward.set()
        try:
            await asyncio.wait_for(stopping.wait(), timeout=2)
            if cancel_twice:
                task.cancel("second cancellation")
        finally:
            release_stop.set()
            with pytest.raises(asyncio.CancelledError, match="original cancellation"):
                await asyncio.wait_for(task, timeout=2)

    assert stopped.is_set()
    remove.assert_awaited_once()
    bridge.stop.assert_awaited_once_with()
    _assert_no_session(manager)
