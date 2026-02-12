"""Tests for BridgeDownloader."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from android_emu_agent.debugger.bridge_downloader import BridgeDownloader
from android_emu_agent.errors import AgentError


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_resolve_uses_cached_jar_when_checksum_matches(tmp_path: Path) -> None:
    jar_bytes = b"bridge-jar"
    expected_sha = _sha256_hex(jar_bytes)
    jar = tmp_path / "jdi-bridge-0.1.10-all.jar"
    checksum = tmp_path / "jdi-bridge-0.1.10-all.jar.sha256"
    jar.write_bytes(jar_bytes)
    checksum.write_text(f"{expected_sha}\n", encoding="utf-8")

    downloader = BridgeDownloader(cache_dir=tmp_path, version="0.1.10", repo="example/repo")
    resolved = downloader.resolve()

    assert resolved == jar


def test_resolve_downloads_when_missing(tmp_path: Path) -> None:
    jar_bytes = b"downloaded-jar"
    expected_sha = _sha256_hex(jar_bytes)
    downloader = BridgeDownloader(cache_dir=tmp_path, version="0.1.10", repo="example/repo")

    with (
        patch.object(downloader, "_download_text", return_value=expected_sha),
        patch.object(downloader, "_download_bytes", return_value=jar_bytes),
    ):
        resolved = downloader.resolve()

    assert resolved.is_file()
    assert resolved.read_bytes() == jar_bytes


def test_resolve_raises_on_checksum_mismatch(tmp_path: Path) -> None:
    jar_bytes = b"actual-bytes"
    wrong_sha = _sha256_hex(b"other-bytes")
    downloader = BridgeDownloader(cache_dir=tmp_path, version="0.1.10", repo="example/repo")

    with (
        patch.object(downloader, "_download_text", return_value=wrong_sha),
        patch.object(downloader, "_download_bytes", return_value=jar_bytes),
        pytest.raises(AgentError) as exc_info,
    ):
        downloader.resolve()

    assert exc_info.value.code == "ERR_BRIDGE_NOT_RUNNING"
