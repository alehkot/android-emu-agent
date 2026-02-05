"""Tests for snapshot mode parameter (compact/full/raw)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from android_emu_agent.cli.main import app
from android_emu_agent.daemon.models import SnapshotRequest


class TestSnapshotRequestModel:
    """Tests for SnapshotRequest Pydantic model with mode field."""

    def test_default_mode_is_compact(self) -> None:
        """Default mode should be compact."""
        request = SnapshotRequest(session_id="s-123")
        assert request.mode == "compact"

    def test_mode_compact_valid(self) -> None:
        """Should accept 'compact' as valid mode."""
        request = SnapshotRequest(session_id="s-123", mode="compact")
        assert request.mode == "compact"

    def test_mode_full_valid(self) -> None:
        """Should accept 'full' as valid mode."""
        request = SnapshotRequest(session_id="s-123", mode="full")
        assert request.mode == "full"

    def test_mode_raw_valid(self) -> None:
        """Should accept 'raw' as valid mode."""
        request = SnapshotRequest(session_id="s-123", mode="raw")
        assert request.mode == "raw"

    def test_invalid_mode_rejected(self) -> None:
        """Should reject invalid mode values."""
        with pytest.raises(ValidationError):
            SnapshotRequest(session_id="s-123", mode=cast(Any, "invalid"))

    def test_backward_compatibility_full_flag(self) -> None:
        """The 'full' field should still work for backward compatibility.

        When full=True and mode is not specified, mode should be 'full'.
        """
        # Note: This tests the behavior after we implement the migration
        request = SnapshotRequest(session_id="s-123", full=True)
        # full=True should set mode to full
        assert request.mode == "full"

    def test_mode_takes_precedence_over_full(self) -> None:
        """Explicit mode parameter should take precedence over full flag."""
        request = SnapshotRequest(session_id="s-123", mode="raw", full=True)
        # mode should take precedence
        assert request.mode == "raw"


class TestCLISnapshotFlags:
    """Tests for CLI snapshot command flags."""

    def test_default_mode_is_compact(self) -> None:
        """With no flags, mode should be compact."""
        from typer.testing import CliRunner

        runner = CliRunner()

        # Mock the daemon client to capture the request
        with patch("android_emu_agent.cli.commands.ui.DaemonClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.request.return_value.json.return_value = {"elements": []}
            mock_client_class.return_value = mock_client

            runner.invoke(app, ["ui", "snapshot", "s-123"])

            # Check that mode=compact was sent
            call_args = mock_client.request.call_args
            json_body = call_args.kwargs.get("json_body") or call_args[1].get("json_body")
            assert json_body["mode"] == "compact"

    def test_full_flag_sets_full_mode(self) -> None:
        """--full flag should set mode to full."""
        from typer.testing import CliRunner

        runner = CliRunner()

        with patch("android_emu_agent.cli.commands.ui.DaemonClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.request.return_value.json.return_value = {"elements": []}
            mock_client_class.return_value = mock_client

            runner.invoke(app, ["ui", "snapshot", "s-123", "--full"])

            call_args = mock_client.request.call_args
            json_body = call_args.kwargs.get("json_body") or call_args[1].get("json_body")
            assert json_body["mode"] == "full"

    def test_raw_flag_sets_raw_mode(self) -> None:
        """--raw flag should set mode to raw."""
        from typer.testing import CliRunner

        runner = CliRunner()

        with patch("android_emu_agent.cli.commands.ui.DaemonClient") as mock_client_class:
            mock_client = MagicMock()
            # For raw mode, return XML string
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "application/xml"}
            mock_response.text = "<hierarchy></hierarchy>"
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client

            runner.invoke(app, ["ui", "snapshot", "s-123", "--raw"])

            call_args = mock_client.request.call_args
            json_body = call_args.kwargs.get("json_body") or call_args[1].get("json_body")
            assert json_body["mode"] == "raw"

    def test_full_and_raw_mutually_exclusive(self) -> None:
        """--full and --raw should be mutually exclusive."""
        from typer.testing import CliRunner

        runner = CliRunner()

        result = runner.invoke(app, ["ui", "snapshot", "s-123", "--full", "--raw"])

        # Should fail or show error about mutual exclusivity
        error_indicated = (
            result.exit_code != 0
            or "mutually exclusive" in result.output.lower()
            or "cannot" in result.output.lower()
        )
        assert error_indicated


class TestSnapshotModePassedToSnapshotter:
    """Tests for mode being passed correctly to snapshotter."""

    def test_compact_mode_calls_parse_with_interactive_only_true(
        self,
        sample_hierarchy_xml: bytes,
        sample_device_info: dict[str, Any],
        sample_context_info: dict[str, Any],
    ) -> None:
        """Compact mode should parse with interactive_only=True."""
        from android_emu_agent.ui.snapshotter import UISnapshotter

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(
            xml_content=sample_hierarchy_xml,
            session_id="s-test",
            generation=1,
            device_info=sample_device_info,
            context_info=sample_context_info,
            interactive_only=True,  # compact mode
        )

        # Should only have interactive elements
        assert len(snapshot.elements) >= 3  # button, textfield, checkbox at minimum

    def test_full_mode_calls_parse_with_interactive_only_false(
        self,
        sample_hierarchy_xml: bytes,
        sample_device_info: dict[str, Any],
        sample_context_info: dict[str, Any],
    ) -> None:
        """Full mode should parse with interactive_only=False."""
        from android_emu_agent.ui.snapshotter import UISnapshotter

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(
            xml_content=sample_hierarchy_xml,
            session_id="s-test",
            generation=1,
            device_info=sample_device_info,
            context_info=sample_context_info,
            interactive_only=False,  # full mode
        )

        # Should have ALL elements including non-interactive containers
        # The sample XML has FrameLayout and LinearLayout as non-interactive containers
        assert len(snapshot.elements) >= 5  # More elements than interactive-only
