"""Tests for daemon package metadata."""

from android_emu_agent import __version__
from android_emu_agent.daemon.server import app


def test_daemon_metadata_uses_package_version() -> None:
    """FastAPI and OpenAPI metadata should stay aligned with release artifacts."""
    assert app.version == __version__
    assert app.openapi()["info"]["version"] == __version__
