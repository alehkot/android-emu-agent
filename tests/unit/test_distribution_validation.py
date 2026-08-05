"""Tests for Python distribution content validation."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

from scripts.validate_distribution import (
    SDIST_SKILL_ROOT,
    WHEEL_SKILL_ROOT,
    validate_distributions,
)


def _skill_files(repo_root: Path) -> list[Path]:
    skill_root = repo_root / SDIST_SKILL_ROOT
    return sorted(path.relative_to(skill_root) for path in skill_root.rglob("*") if path.is_file())


def _write_wheel(path: Path, skill_files: list[Path], *, include_skills: bool = True) -> None:
    with zipfile.ZipFile(path, mode="w") as wheel:
        wheel.writestr("android_emu_agent/__init__.py", "")
        if include_skills:
            for relative_path in skill_files:
                wheel.writestr((WHEEL_SKILL_ROOT / relative_path).as_posix(), "skill")


def _write_sdist(path: Path, skill_files: list[Path], *, include_bridge: bool = False) -> None:
    root = "android_emu_agent-0.1.15"
    names = [f"{root}/src/android_emu_agent/__init__.py"]
    names.extend(f"{root}/{(SDIST_SKILL_ROOT / item).as_posix()}" for item in skill_files)
    if include_bridge:
        names.append(f"{root}/jdi-bridge/src/test/kotlin/BridgeTest.kt")

    with tarfile.open(path, mode="w:gz") as sdist:
        for name in names:
            payload = b"content"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            sdist.addfile(info, io.BytesIO(payload))


def test_distribution_validator_accepts_bundled_skill_without_bridge(tmp_path: Path) -> None:
    """A complete skill and focused Python source archive should pass."""
    repo_root = Path(__file__).resolve().parents[2]
    skill_files = _skill_files(repo_root)
    wheel = tmp_path / "package.whl"
    sdist = tmp_path / "package.tar.gz"
    _write_wheel(wheel, skill_files)
    _write_sdist(sdist, skill_files)

    assert validate_distributions(wheel, sdist, repo_root=repo_root) == []


def test_distribution_validator_reports_missing_skill_and_bridge_sources(tmp_path: Path) -> None:
    """Missing wheel skill data and leaked bridge sources should both fail."""
    repo_root = Path(__file__).resolve().parents[2]
    skill_files = _skill_files(repo_root)
    wheel = tmp_path / "package.whl"
    sdist = tmp_path / "package.tar.gz"
    _write_wheel(wheel, skill_files, include_skills=False)
    _write_sdist(sdist, skill_files, include_bridge=True)

    errors = validate_distributions(wheel, sdist, repo_root=repo_root)

    assert any("wheel is missing bundled skill file" in error for error in errors)
    assert "sdist unexpectedly contains jdi-bridge sources" in errors
