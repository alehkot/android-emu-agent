"""Mapping inputs belong to the invoking CLI, not the daemon or JVM directory."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from android_emu_agent.cli.commands import debug
from android_emu_agent.cli.main import app
from android_emu_agent.daemon import server
from android_emu_agent.debugger.manager import DebugManager


@pytest.mark.parametrize("spelling", ["relative", "absolute", "home", "spaces", "symlink-parent"])
def test_mapping_load_reads_caller_file_not_daemon_decoy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    caller = tmp_path / "caller"
    daemon = tmp_path / "daemon"
    home = tmp_path / "home"
    for directory in (caller, daemon, home):
        directory.mkdir()
    source = caller / "mapping.txt"
    raw = "mapping.txt"
    if spelling == "absolute":
        raw = str(source)
    elif spelling == "home":
        source = home / "mapping.txt"
        raw = "~/mapping.txt"
    elif spelling == "spaces":
        source = caller / "release mappings" / "карта.txt"
        source.parent.mkdir()
        raw = "release mappings/карта.txt"
    elif spelling == "symlink-parent":
        target = home / "nested"
        target.mkdir()
        (caller / "link").symlink_to(target, target_is_directory=True)
        source = home / "mapping.txt"
        raw = "link/../mapping.txt"
    source.write_text("com.example.CorrectBuild -> a:\n", encoding="utf-8")
    (daemon / "mapping.txt").write_text("com.example.WrongBuild -> a:\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(caller)
    read_contents: list[str] = []
    requested_paths: list[str] = []

    async def bridge_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert method == "load_mapping"
        requested_paths.append(params["path"])
        read_contents.append(Path(params["path"]).read_text(encoding="utf-8"))
        return {"status": "loaded", "path": params["path"], "class_count": 1}

    manager = DebugManager()
    manager.get_bridge = AsyncMock(return_value=SimpleNamespace(request=bridge_request))
    core = SimpleNamespace(
        debug_manager=manager,
        session_manager=SimpleNamespace(get_session=AsyncMock(return_value=object())),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs == {"timeout": 30.0}

        def request(self, method: str, path: str, *, json_body: dict[str, Any]):
            assert (method, path) == ("POST", "/debug/mapping/load")
            with monkeypatch.context() as daemon_context:
                daemon_context.chdir(daemon)
                return api.request(method, path, json=json_body)

        def close(self) -> None:
            api.close()

    monkeypatch.setattr(debug, "DaemonClient", Client)
    result = CliRunner().invoke(
        app, ["debug", "mapping", "load", raw, "--session", "s-test", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert read_contents == ["com.example.CorrectBuild -> a:\n"]
    assert Path(requested_paths[0]).is_absolute()
    assert json.loads(result.output)["path"] == requested_paths[0]
    if spelling == "symlink-parent":
        assert requested_paths[0] == str(caller / "link" / ".." / "mapping.txt")


@pytest.mark.parametrize("raw", ["", "   "])
def test_mapping_load_preserves_empty_path_rejection(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    manager = SimpleNamespace(load_mapping=AsyncMock())
    core = SimpleNamespace(
        debug_manager=manager,
        session_manager=SimpleNamespace(get_session=AsyncMock(return_value=object())),
    )
    monkeypatch.setattr(server.app.state, "core", core, raising=False)
    api = TestClient(server.app)

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def request(self, method: str, path: str, *, json_body: dict[str, Any]):
            return api.request(method, path, json=json_body)

        def close(self) -> None:
            api.close()

    monkeypatch.setattr(debug, "DaemonClient", Client)
    result = CliRunner().invoke(
        app, ["debug", "mapping", "load", raw, "--session", "s-test", "--json"]
    )
    assert result.exit_code == 1, result.output
    assert "ERR_INVALID_MAPPING_PATH" in result.output
    manager.load_mapping.assert_not_awaited()
