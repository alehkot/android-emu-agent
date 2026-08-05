"""Tests for BridgeClient JSON-RPC communication."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_emu_agent.debugger.bridge_client import BridgeClient
from android_emu_agent.errors import AgentError


class TestBridgeClientRequestFormat:
    """Tests for JSON-RPC request/response formatting."""

    def test_initial_state(self) -> None:
        """Bridge should not be alive before start."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))
        assert not client.is_alive

    @pytest.mark.asyncio
    async def test_ping_round_trip(self) -> None:
        """Ping should send JSON-RPC and parse the response."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))

        # Create a mock process
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 12345

        # Mock stdin
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()

        # Mock stdout: return a ping response then EOF
        response_line = (
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"pong": True}, "error": None}
            ).encode()
            + b"\n"
        )
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[response_line, b""])

        # Mock stderr: immediate EOF
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = AsyncMock(return_value=b"")

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            await client.start()
            result = await client.ping()

        assert result == {"pong": True}

        # Verify the request was written to stdin
        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        req = json.loads(written.decode())
        assert req["jsonrpc"] == "2.0"
        assert req["method"] == "ping"
        assert req["id"] == 1

    @pytest.mark.asyncio
    async def test_not_alive_raises(self) -> None:
        """Request on a non-started bridge should raise."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))
        with pytest.raises(AgentError) as exc_info:
            await client.request("ping")
        assert exc_info.value.code == "ERR_BRIDGE_CRASHED"

    @pytest.mark.asyncio
    async def test_request_honors_operation_timeout(self) -> None:
        """Long debugger operations should override the default RPC deadline."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))
        mock_proc = MagicMock(returncode=None)
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        client._process = mock_proc

        with (
            patch("asyncio.wait_for", AsyncMock(side_effect=TimeoutError)) as wait_for,
            pytest.raises(AgentError) as exc_info,
        ):
            await client.request("step_over", timeout_seconds=75.0)

        assert exc_info.value.code == "ERR_BRIDGE_CRASHED"
        assert "75s" in exc_info.value.message
        assert wait_for.await_args is not None
        assert wait_for.await_args.kwargs["timeout"] == 75.0


class TestBridgeClientLifecycle:
    """Tests for bridge subprocess lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        """Stopping a never-started bridge should be a no-op."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))
        await client.stop()  # Should not raise
        assert not client.is_alive

    @pytest.mark.asyncio
    async def test_unexpected_stdout_eof_emits_disconnect_event(self) -> None:
        """An exited bridge should wake the manager's lifecycle monitor."""
        client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))
        mock_proc = MagicMock(returncode=17)
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        client._process = mock_proc

        await client._read_stdout_loop()

        event = await client.next_event()
        assert event["method"] == "event"
        assert event["params"] == {
            "type": "bridge_disconnected",
            "reason": "bridge_crashed",
            "detail": "bridge stdout closed",
            "returncode": 17,
        }

    @pytest.mark.asyncio
    async def test_event_queue_keeps_newest_notifications(self) -> None:
        """A notification storm should not block stdout processing or grow without bound."""
        with patch("android_emu_agent.debugger.bridge_client._MAX_BRIDGE_EVENTS", 2):
            client = BridgeClient(Path("/usr/bin/java"), Path("/tmp/fake.jar"))

        client._queue_event({"sequence": 1})
        client._queue_event({"sequence": 2})
        client._queue_event({"sequence": 3})

        assert await client.next_event() == {"sequence": 2}
        assert await client.next_event() == {"sequence": 3}
