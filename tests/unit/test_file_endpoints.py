"""Tests for file-related daemon endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


@dataclass
class DummyInfo:
    is_rooted: bool


class DummyDeviceManager:
    def __init__(self, device: object, info: DummyInfo | None) -> None:
        self._device = device
        self._info = info

    async def get_adb_device(self, serial: str) -> object | None:
        if serial != "emulator-5554":
            return None
        return self._device

    async def get_device(self, serial: str) -> DummyInfo | None:
        if serial != "emulator-5554":
            return None
        return self._info


class DummySessionManager:
    async def get_session(self, _session_id: str) -> Any | None:
        return None


class DummyFileManager:
    def __init__(self, matches: list[dict[str, Any]]) -> None:
        self.matches = matches
        self.find_calls: list[tuple[object, str, str, str, int, bool]] = []
        self.list_calls: list[tuple[object, str, str, bool]] = []
        self.app_pull_calls: list[tuple[object, str, str, str, str | None, bool]] = []

    async def find_metadata(
        self,
        device: object,
        path: str,
        name: str,
        kind: str,
        max_depth: int,
        *,
        use_root: bool,
    ) -> list[dict[str, Any]]:
        self.find_calls.append((device, path, name, kind, max_depth, use_root))
        return self.matches

    async def list_metadata(
        self,
        device: object,
        path: str,
        kind: str,
        *,
        use_root: bool,
    ) -> list[dict[str, Any]]:
        self.list_calls.append((device, path, kind, use_root))
        return self.matches

    async def app_pull(
        self,
        device: object,
        serial: str,
        package: str,
        remote_path: str,
        local_path: str | None,
        *,
        use_root: bool,
    ) -> str:
        self.app_pull_calls.append((device, serial, package, remote_path, local_path, use_root))
        return "/tmp/pulled.json"


class DummyCore:
    device_manager: DummyDeviceManager
    session_manager: DummySessionManager
    file_manager: DummyFileManager
    last: DummyCore | None = None

    def __init__(self) -> None:
        self.device_manager = self.__class__.device_manager
        self.session_manager = self.__class__.session_manager
        self.file_manager = self.__class__.file_manager
        self._running = False
        self.__class__.last = self

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


@contextmanager
def _client_with_core(
    *,
    info: DummyInfo,
    matches: list[dict[str, Any]],
) -> Any:
    from android_emu_agent.daemon import server

    file_manager = DummyFileManager(matches)
    DummyCore.device_manager = DummyDeviceManager(device=object(), info=info)
    DummyCore.session_manager = DummySessionManager()
    DummyCore.file_manager = file_manager

    with patch.object(server, "DaemonCore", DummyCore), TestClient(server.app) as client:
        yield client, file_manager


def test_files_find_success() -> None:
    """Should return matches and format output."""
    matches = [
        {
            "path": "/data/data/app/db.sqlite",
            "name": "db.sqlite",
            "kind": "file",
            "type_raw": "regular file",
            "size_bytes": 2048,
            "uid": 1000,
            "gid": 1000,
            "mode": "644",
            "mtime_epoch": 1700000000,
        }
    ]
    with _client_with_core(info=DummyInfo(is_rooted=True), matches=matches) as (
        client,
        file_manager,
    ):
        resp = client.post(
            "/files/find",
            json={
                "serial": "emulator-5554",
                "path": "/data/data",
                "name": "*.db",
                "kind": "file",
                "max_depth": 2,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["count"] == 1
    assert data["results"] == matches
    assert "PATH\tTYPE\tSIZE" in data["output"]
    assert "/data/data/app/db.sqlite" in data["output"]
    assert len(file_manager.find_calls) == 1
    _device, path, name, kind, depth, use_root = file_manager.find_calls[0]
    assert (path, name, kind, depth, use_root) == ("/data/data", "*.db", "file", 2, True)


def test_files_list_success() -> None:
    """Should list directory entries with metadata."""
    matches = [
        {
            "path": "/sdcard/Download",
            "name": "Download",
            "kind": "dir",
            "type_raw": "directory",
            "size_bytes": 4096,
            "uid": 1000,
            "gid": 1000,
            "mode": "755",
            "mtime_epoch": 1700000100,
        }
    ]
    with _client_with_core(info=DummyInfo(is_rooted=True), matches=matches) as (
        client,
        file_manager,
    ):
        resp = client.post(
            "/files/list",
            json={
                "serial": "emulator-5554",
                "path": "/sdcard",
                "kind": "dir",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["count"] == 1
    assert data["results"] == matches
    assert len(file_manager.list_calls) == 1
    _device, path, kind, use_root = file_manager.list_calls[0]
    assert (path, kind, use_root) == ("/sdcard", "dir", True)


def test_files_find_uses_direct_shell_without_root() -> None:
    """Non-root targets should search paths available to the shell user."""
    with _client_with_core(info=DummyInfo(is_rooted=False), matches=[]) as (
        client,
        _file_manager,
    ):
        resp = client.post(
            "/files/find",
            json={
                "serial": "emulator-5554",
                "path": "/data/data",
                "name": "*.db",
            },
        )

    assert resp.status_code == 200
    assert DummyCore.last is not None
    assert DummyCore.last.file_manager.find_calls[0][-1] is False


def test_files_list_uses_direct_shell_without_root() -> None:
    """Non-root targets should list paths available to the shell user."""
    with _client_with_core(info=DummyInfo(is_rooted=False), matches=[]) as (
        client,
        _file_manager,
    ):
        resp = client.post(
            "/files/list",
            json={
                "serial": "emulator-5554",
                "path": "/sdcard",
            },
        )

    assert resp.status_code == 200
    assert DummyCore.last is not None
    assert DummyCore.last.file_manager.list_calls[0][-1] is False


def test_files_app_pull_uses_run_as_path_without_root() -> None:
    """Non-root targets should let the manager use run-as for debuggable apps."""
    with _client_with_core(info=DummyInfo(is_rooted=False), matches=[]) as (
        client,
        file_manager,
    ):
        resp = client.post(
            "/files/app_pull",
            json={
                "serial": "emulator-5554",
                "package": "com.example.app",
                "remote_path": "files/config.json",
            },
        )

    assert resp.status_code == 200
    assert file_manager.app_pull_calls[0][-1] is False
