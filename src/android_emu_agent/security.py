"""Filesystem permission helpers for daemon-owned state."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TextIO

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
PERMISSIONS_MARKER = ".permissions-v1"


def ensure_private_directory(path: Path) -> None:
    """Create a directory if needed and restrict it to the current user."""
    path.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    file_stat = path.lstat()
    if not stat.S_ISDIR(file_stat.st_mode) or path.is_symlink():
        raise RuntimeError(f"Refusing to use non-directory state path: {path}")
    path.chmod(PRIVATE_DIRECTORY_MODE)


def ensure_private_file(path: Path) -> None:
    """Restrict an existing regular file to the current user."""
    if not path.exists():
        return
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode) or path.is_symlink():
        raise RuntimeError(f"Refusing to use non-file state path: {path}")
    path.chmod(PRIVATE_FILE_MODE)


def secure_private_tree(root: Path) -> None:
    """Migrate an existing daemon state tree to owner-only permissions."""
    ensure_private_directory(root)
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        file_stat = path.lstat()
        if stat.S_ISDIR(file_stat.st_mode):
            path.chmod(PRIVATE_DIRECTORY_MODE)
        elif stat.S_ISREG(file_stat.st_mode):
            path.chmod(PRIVATE_FILE_MODE)


def migrate_private_tree(root: Path) -> None:
    """Secure legacy state once without scanning the tree on every CLI call."""
    ensure_private_directory(root)
    marker = root / PERMISSIONS_MARKER
    if marker.exists():
        ensure_private_file(marker)
        return
    secure_private_tree(root)
    write_private_text(marker, "owner-only\n")


def secure_socket(path: Path) -> None:
    """Validate and restrict an existing Unix socket before using it."""
    if not path.exists():
        return
    file_stat = path.lstat()
    if not stat.S_ISSOCK(file_stat.st_mode):
        raise RuntimeError(f"Refusing to use non-socket daemon path: {path}")
    if hasattr(os, "getuid") and file_stat.st_uid != os.getuid():
        raise RuntimeError(f"Refusing to use daemon socket owned by another user: {path}")
    path.chmod(PRIVATE_FILE_MODE)


def open_private_append(path: Path) -> TextIO:
    """Open a private append-only text file without following symlinks."""
    ensure_private_directory(path.parent)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    return os.fdopen(descriptor, "a", encoding="utf-8")


def write_private_text(path: Path, value: str) -> None:
    """Replace a private text file without following symlinks."""
    ensure_private_directory(path.parent)
    flags = os.O_CREAT | os.O_TRUNC | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        handle.write(value)
