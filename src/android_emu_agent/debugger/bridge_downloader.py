"""Bridge JAR resolver/downloader with checksum verification."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

from android_emu_agent.errors import bridge_not_running_error

_DEFAULT_BRIDGE_REPO = "alehkot/android-emu-agent"
_DEFAULT_BRIDGE_VERSION = "0.1.10"
_DEFAULT_TIMEOUT_SECS = 20


class BridgeDownloader:
    """Resolves a cached JDI Bridge JAR and downloads it from GitHub releases if needed."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        repo: str | None = None,
        version: str | None = None,
        tag: str | None = None,
    ) -> None:
        self._cache_dir = cache_dir or (Path.home() / ".android-emu-agent" / "bridge")
        self._repo = repo or os.environ.get("ANDROID_EMU_AGENT_BRIDGE_REPO", _DEFAULT_BRIDGE_REPO)
        self._version = version or os.environ.get(
            "ANDROID_EMU_AGENT_BRIDGE_VERSION",
            _DEFAULT_BRIDGE_VERSION,
        )
        self._tag = tag or os.environ.get("ANDROID_EMU_AGENT_BRIDGE_TAG", f"v{self._version}")

    def resolve(self) -> Path:
        """Return a verified local JAR path, downloading if needed."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        jar_path = self._cache_dir / self._jar_name
        checksum_path = jar_path.with_suffix(".jar.sha256")

        expected_sha = self._resolve_expected_sha(checksum_path)

        if jar_path.is_file() and self._verify_sha(jar_path, expected_sha):
            return jar_path

        self._download_jar(jar_path, expected_sha)
        return jar_path

    @property
    def _jar_name(self) -> str:
        return f"jdi-bridge-{self._version}-all.jar"

    @property
    def _jar_url(self) -> str:
        return f"https://github.com/{self._repo}/releases/download/{self._tag}/{self._jar_name}"

    @property
    def _checksum_url(self) -> str:
        return (
            f"https://github.com/{self._repo}/releases/download/{self._tag}/{self._jar_name}.sha256"
        )

    def _resolve_expected_sha(self, checksum_path: Path) -> str:
        if checksum_path.is_file():
            try:
                return self._parse_checksum_text(checksum_path.read_text(encoding="utf-8"))
            except ValueError:
                checksum_path.unlink(missing_ok=True)

        text = self._download_text(self._checksum_url)
        expected_sha = self._parse_checksum_text(text)
        checksum_path.write_text(f"{expected_sha}\n", encoding="utf-8")
        return expected_sha

    def _download_jar(self, jar_path: Path, expected_sha: str) -> None:
        tmp_path = jar_path.with_suffix(".jar.tmp")
        jar_bytes = self._download_bytes(self._jar_url)
        tmp_path.write_bytes(jar_bytes)

        if not self._verify_sha(tmp_path, expected_sha):
            tmp_path.unlink(missing_ok=True)
            raise bridge_not_running_error(
                f"Downloaded bridge JAR checksum mismatch for {self._jar_name}"
            )

        tmp_path.replace(jar_path)

    def _download_text(self, url: str) -> str:
        return self._download_bytes(url).decode("utf-8").strip()

    def _download_bytes(self, url: str) -> bytes:
        try:
            with request.urlopen(url, timeout=_DEFAULT_TIMEOUT_SECS) as response:
                data = response.read()
                if isinstance(data, bytes):
                    return data
                return bytes(data)
        except (HTTPError, URLError, OSError) as exc:
            raise bridge_not_running_error(
                f"Failed to download bridge artifact: {url} ({exc})"
            ) from None

    @staticmethod
    def _verify_sha(path: Path, expected_sha: str) -> bool:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest.lower() == expected_sha.lower()

    @staticmethod
    def _parse_checksum_text(raw_text: str) -> str:
        token = raw_text.strip().split()[0] if raw_text.strip() else ""
        if len(token) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in token):
            raise ValueError("Invalid SHA-256 checksum")
        return token
