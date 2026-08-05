"""File manager - push/pull files to device and app data."""

from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import structlog

from android_emu_agent.errors import (
    AgentError,
    adb_command_error,
    adb_not_found_error,
    file_not_found_error,
)

if TYPE_CHECKING:
    from adbutils import AdbDevice

logger = structlog.get_logger()


class FileMatch(TypedDict):
    path: str
    name: str
    kind: str
    type_raw: str
    size_bytes: int
    uid: int
    gid: int
    mode: str
    mtime_epoch: int


class FileManager:
    """Push and pull files via adb."""

    _FIND_DELIMITER = "|"
    _FIND_FORMAT = "%n|%F|%s|%u|%g|%a|%Y"
    _SHELL_EXIT_MARKER = "__AEA_EXIT_CODE__:"

    def __init__(self, output_dir: Path | None = None) -> None:
        default_dir = Path.home() / ".android-emu-agent" / "artifacts" / "files"
        self.output_dir = output_dir or default_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def push(self, serial: str, local_path: str, remote_path: str | None) -> str:
        local = Path(local_path).expanduser()
        if not local.exists():
            raise file_not_found_error(str(local))
        if remote_path is None:
            remote_path = f"/sdcard/Download/{local.name}"

        await self._run_adb(serial, ["push", str(local), remote_path])
        logger.info("file_pushed", serial=serial, local=str(local), remote=remote_path)
        return remote_path

    async def pull(self, serial: str, remote_path: str, local_path: str | None) -> Path:
        local = self._resolve_local_path(serial, remote_path, local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        await self._run_adb(serial, ["pull", remote_path, str(local)])
        logger.info("file_pulled", serial=serial, remote=remote_path, local=str(local))
        return local

    async def app_pull(
        self,
        device: AdbDevice,
        serial: str,
        package: str,
        remote_path: str,
        local_path: str | None,
        *,
        use_root: bool,
    ) -> Path:
        remote_abs = self._resolve_app_path(package, remote_path)
        local = self._resolve_local_path(serial, remote_path, local_path, prefix=f"{package}_")
        local.parent.mkdir(parents=True, exist_ok=True)
        if not use_root:
            await self._app_pull_run_as(device, serial, package, remote_abs, local)
            logger.info("app_file_pulled", serial=serial, remote=remote_abs, local=str(local))
            return local

        stage_dir = self._stage_dir(package)
        stage_path = f"{stage_dir}/{self._stage_name(package)}"
        prepare_parts = [
            f"rm -rf {shlex.quote(stage_path)}",
            f"mkdir -p {shlex.quote(stage_dir)}",
            f"chmod 0733 {shlex.quote(stage_dir)}",
        ]
        await self._shell_with_optional_root(
            device,
            " && ".join(prepare_parts),
            use_root=use_root,
        )
        stage_cmd = " && ".join(
            [
                f"cp -r {shlex.quote(remote_abs)} {shlex.quote(stage_path)}",
                f"chmod -R a+rX {shlex.quote(stage_path)}",
            ]
        )

        try:
            await self._shell_app(device, package, stage_cmd, use_root=use_root)
            await self._run_adb(serial, ["pull", stage_path, str(local)])
        finally:
            await self._shell(device, f"rm -rf {shlex.quote(stage_path)}")
        logger.info("app_file_pulled", serial=serial, remote=remote_abs, local=str(local))
        return local

    async def _app_pull_run_as(
        self,
        device: AdbDevice,
        serial: str,
        package: str,
        remote_abs: str,
        local: Path,
    ) -> None:
        """Pull app data without copying it across SELinux domains on-device."""
        safe_remote = shlex.quote(remote_abs)
        kind_command = (
            f"if [ -f {safe_remote} ]; then printf file; "
            f"elif [ -d {safe_remote} ]; then printf dir; else exit 44; fi"
        )
        kind = await self._shell_app(device, package, kind_command, use_root=False)
        if kind == "file":
            destination = local / Path(remote_abs).name if local.is_dir() else local
            await self._run_adb_to_file(
                serial,
                ["exec-out", "run-as", package, "cat", remote_abs],
                destination,
            )
            return
        if kind != "dir":
            raise file_not_found_error(remote_abs)

        await self._pull_app_directory(serial, package, remote_abs, local)

    async def _pull_app_directory(
        self,
        serial: str,
        package: str,
        remote_abs: str,
        local: Path,
    ) -> None:
        """Stream and safely extract an app-private directory through adb exec-out."""

        def _extract(archive_path: Path, extract_root: Path) -> None:
            with tarfile.open(archive_path, mode="r:*") as archive:
                for member in archive.getmembers():
                    target = (extract_root / member.name).resolve()
                    if not target.is_relative_to(extract_root.resolve()):
                        raise self._unsafe_archive_error(member.name)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        raise self._unsafe_archive_error(member.name)
                    source = archive.extractfile(member)
                    if source is None:
                        raise self._unsafe_archive_error(member.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)

            local.mkdir(parents=True, exist_ok=True)
            shutil.copytree(extract_root, local, dirs_exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="aea-app-pull-") as temp_dir:
            temp_root = Path(temp_dir)
            archive_path = temp_root / "payload.tar"
            extract_root = temp_root / "extracted"
            extract_root.mkdir()
            await self._run_adb_to_file(
                serial,
                [
                    "exec-out",
                    "run-as",
                    package,
                    "tar",
                    "-C",
                    remote_abs,
                    "-cf",
                    "-",
                    ".",
                ],
                archive_path,
            )
            await asyncio.to_thread(_extract, archive_path, extract_root)

    async def app_push(
        self,
        device: AdbDevice,
        serial: str,
        package: str,
        local_path: str,
        remote_path: str | None,
        *,
        use_root: bool,
    ) -> str:
        local = Path(local_path).expanduser()
        if not local.exists():
            raise file_not_found_error(str(local))

        remote_abs = self._resolve_app_dest(package, remote_path, local.name)
        stage_dir = self._stage_dir(package)
        stage_path = f"{stage_dir}/{self._stage_name(package, local.name)}"

        await self._shell_with_optional_root(
            device,
            f"mkdir -p {shlex.quote(stage_dir)} && chmod 0733 {shlex.quote(stage_dir)}",
            use_root=use_root,
        )
        dest_parent = str(Path(remote_abs).parent)
        stage_cmd = (
            f"mkdir -p {shlex.quote(dest_parent)} "
            f"&& cp -r {shlex.quote(stage_path)} {shlex.quote(remote_abs)}"
        )
        try:
            await self._run_adb(serial, ["push", str(local), stage_path])
            await self._shell_app(device, package, stage_cmd, use_root=use_root)
        finally:
            await self._shell(device, f"rm -rf {shlex.quote(stage_path)}")
        logger.info("app_file_pushed", serial=serial, local=str(local), remote=remote_abs)
        return remote_abs

    async def find_metadata(
        self,
        device: AdbDevice,
        path: str,
        name: str,
        kind: str,
        max_depth: int,
        *,
        use_root: bool = False,
    ) -> list[FileMatch]:
        if max_depth < 0:
            raise AgentError(
                code="ERR_INVALID_DEPTH",
                message=f"Invalid max depth: {max_depth}",
                context={"max_depth": max_depth},
                remediation="Provide --max-depth 0 or greater.",
            )

        type_flag = ""
        if kind == "file":
            type_flag = "-type f"
        elif kind == "dir":
            type_flag = "-type d"

        safe_path = shlex.quote(path)
        safe_name = shlex.quote(name)
        safe_format = shlex.quote(self._FIND_FORMAT)
        depth_flag = f"-maxdepth {max_depth}"
        parts = [
            "find",
            "-H",
            safe_path,
            depth_flag,
            type_flag,
            "-name",
            safe_name,
            "-exec",
            "stat",
            "-c",
            safe_format,
            "{}",
            "+",
        ]
        cmd = " ".join(part for part in parts if part)
        output = await self._shell_with_optional_root(device, cmd, use_root=use_root)
        return self._parse_find_output(output)

    async def list_metadata(
        self,
        device: AdbDevice,
        path: str,
        kind: str,
        *,
        use_root: bool = False,
    ) -> list[FileMatch]:
        type_flag = ""
        if kind == "file":
            type_flag = "-type f"
        elif kind == "dir":
            type_flag = "-type d"

        safe_path = shlex.quote(path)
        safe_format = shlex.quote(self._FIND_FORMAT)
        parts = [
            "find",
            "-H",
            safe_path,
            "-mindepth 1",
            "-maxdepth 1",
            type_flag,
            "-exec",
            "stat",
            "-c",
            safe_format,
            "{}",
            "+",
        ]
        cmd = " ".join(part for part in parts if part)
        output = await self._shell_with_optional_root(device, cmd, use_root=use_root)
        return self._parse_find_output(output)

    def _resolve_local_path(
        self,
        serial: str,
        remote_path: str,
        local_path: str | None,
        prefix: str | None = None,
    ) -> Path:
        if local_path:
            return Path(local_path).expanduser()
        timestamp = self._timestamp()
        base = Path(remote_path).name or "artifact"
        prefix_value = prefix or ""
        filename = f"{prefix_value}{serial}_{timestamp}_{base}"
        return self.output_dir / filename

    def _resolve_app_path(self, package: str, remote_path: str) -> str:
        if remote_path.startswith("/"):
            return remote_path
        return f"/data/data/{package}/{remote_path}"

    def _resolve_app_dest(self, package: str, remote_path: str | None, basename: str) -> str:
        if not remote_path:
            return f"/data/data/{package}/files/{basename}"
        if remote_path.endswith("/"):
            return f"{self._resolve_app_path(package, remote_path.rstrip('/'))}/{basename}"
        return self._resolve_app_path(package, remote_path)

    def _stage_dir(self, package: str) -> str:
        safe_pkg = package.replace(".", "_")
        return f"/data/local/tmp/android-emu-agent/{safe_pkg}"

    def _stage_name(self, package: str, suffix: str | None = None) -> str:
        safe_pkg = package.replace(".", "_")
        suffix_part = f"_{suffix}" if suffix else ""
        return f"stage_{safe_pkg}_{self._timestamp()}{suffix_part}"

    def _parse_find_output(self, output: str) -> list[FileMatch]:
        matches: list[FileMatch] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split(self._FIND_DELIMITER)
            if len(parts) != 7:
                continue
            path, type_raw, size, uid, gid, mode, mtime = parts
            try:
                size_bytes = int(size)
                uid_value = int(uid)
                gid_value = int(gid)
                mtime_epoch = int(mtime)
            except ValueError:
                continue

            matches.append(
                {
                    "path": path,
                    "name": Path(path).name,
                    "kind": self._normalize_kind(type_raw),
                    "type_raw": type_raw,
                    "size_bytes": size_bytes,
                    "uid": uid_value,
                    "gid": gid_value,
                    "mode": mode,
                    "mtime_epoch": mtime_epoch,
                }
            )
        return matches

    @staticmethod
    def _normalize_kind(type_raw: str) -> str:
        lowered = type_raw.lower()
        if "directory" in lowered:
            return "dir"
        if "regular file" in lowered:
            return "file"
        if "symbolic link" in lowered:
            return "link"
        if "socket" in lowered:
            return "socket"
        if "fifo" in lowered or "named pipe" in lowered:
            return "fifo"
        if "block" in lowered:
            return "block"
        if "character" in lowered:
            return "char"
        return "other"

    async def _shell(self, device: AdbDevice, command: str) -> str:
        def _run() -> str:
            wrapped = (
                f"{command}; _aea_exit_code=$?; "
                f"printf '\\n{self._SHELL_EXIT_MARKER}%s' \"$_aea_exit_code\""
            )
            result = device.shell(wrapped)
            output = getattr(result, "output", None)
            if isinstance(output, str):
                raw_output = output
            elif isinstance(result, bytes):
                raw_output = result.decode("utf-8", errors="replace")
            else:
                raw_output = str(result)

            body, marker, raw_exit_code = raw_output.rpartition(self._SHELL_EXIT_MARKER)
            if not marker or not raw_exit_code.strip().isdigit():
                raise adb_command_error(command, "Device shell did not report an exit status")
            exit_code = int(raw_exit_code.strip())
            body = body.rstrip("\r\n")
            if exit_code != 0:
                reason = body.strip() or f"exit status {exit_code}"
                raise adb_command_error(command, reason)
            return body

        return await asyncio.to_thread(_run)

    async def _shell_su(self, device: AdbDevice, command: str) -> str:
        return await self._shell(device, f"su -c {shlex.quote(command)}")

    async def _shell_with_optional_root(
        self,
        device: AdbDevice,
        command: str,
        *,
        use_root: bool,
    ) -> str:
        if use_root:
            return await self._shell_su(device, command)
        return await self._shell(device, command)

    async def _shell_app(
        self,
        device: AdbDevice,
        package: str,
        command: str,
        *,
        use_root: bool,
    ) -> str:
        if use_root:
            return await self._shell_su(device, command)
        run_as_command = f"run-as {shlex.quote(package)} sh -c {shlex.quote(command)}"
        return await self._shell(device, run_as_command)

    async def _run_adb(self, serial: str, args: list[str]) -> subprocess.CompletedProcess[str]:
        def _run() -> subprocess.CompletedProcess[str]:
            adb_path = shutil.which("adb")
            if not adb_path:
                raise adb_not_found_error()
            return subprocess.run(
                [adb_path, "-s", serial, *args],
                check=True,
                capture_output=True,
                text=True,
            )

        try:
            return await asyncio.to_thread(_run)
        except AgentError:
            raise
        except FileNotFoundError as exc:
            raise adb_not_found_error() from exc
        except subprocess.CalledProcessError as exc:
            reason = (exc.stderr or exc.stdout or str(exc)).strip()
            raise adb_command_error(" ".join(args), reason) from exc

    async def _run_adb_to_file(self, serial: str, args: list[str], destination: Path) -> None:
        """Run adb with binary stdout written directly to a host file."""

        def _run() -> None:
            adb_path = shutil.which("adb")
            if not adb_path:
                raise adb_not_found_error()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                subprocess.run(
                    [adb_path, "-s", serial, *args],
                    check=True,
                    stdout=output,
                    stderr=subprocess.PIPE,
                )

        try:
            await asyncio.to_thread(_run)
        except AgentError:
            raise
        except FileNotFoundError as exc:
            raise adb_not_found_error() from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            reason = stderr.strip() or str(exc)
            raise adb_command_error(" ".join(args), reason) from exc

    @staticmethod
    def _unsafe_archive_error(member_name: str) -> AgentError:
        return AgentError(
            code="ERR_UNSAFE_ARCHIVE",
            message="Refusing to extract an unsafe app-data archive entry",
            context={"member": member_name},
            remediation="Pull a regular file or directory without links or special entries.",
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")
