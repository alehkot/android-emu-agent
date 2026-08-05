#!/usr/bin/env python3
"""Validate files included in Python release distributions."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_SKILL_ROOT = Path("android_emu_agent/skills/android-emu-agent")
SDIST_SKILL_ROOT = Path("skills/android-emu-agent")


def _expected_skill_files(repo_root: Path) -> list[Path]:
    skill_root = repo_root / SDIST_SKILL_ROOT
    return sorted(path.relative_to(skill_root) for path in skill_root.rglob("*") if path.is_file())


def _sdist_root(names: set[str]) -> str | None:
    roots = {name.split("/", maxsplit=1)[0] for name in names if "/" in name}
    if len(roots) != 1:
        return None
    return roots.pop()


def validate_distributions(
    wheel_path: Path,
    sdist_path: Path,
    *,
    repo_root: Path,
) -> list[str]:
    """Return validation errors for a wheel and source distribution pair."""
    errors: list[str] = []
    expected_skills = _expected_skill_files(repo_root)

    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_names = set(wheel.namelist())
    if "android_emu_agent/__init__.py" not in wheel_names:
        errors.append("wheel is missing android_emu_agent/__init__.py")
    for relative_path in expected_skills:
        expected = (WHEEL_SKILL_ROOT / relative_path).as_posix()
        if expected not in wheel_names:
            errors.append(f"wheel is missing bundled skill file: {expected}")
    if any("/jdi-bridge/" in f"/{name}" for name in wheel_names):
        errors.append("wheel unexpectedly contains jdi-bridge sources")

    with tarfile.open(sdist_path, mode="r:gz") as sdist:
        sdist_names = set(sdist.getnames())
    root = _sdist_root(sdist_names)
    if root is None:
        errors.append("sdist does not have exactly one top-level directory")
        return errors

    if f"{root}/src/android_emu_agent/__init__.py" not in sdist_names:
        errors.append("sdist is missing src/android_emu_agent/__init__.py")
    for relative_path in expected_skills:
        expected = f"{root}/{(SDIST_SKILL_ROOT / relative_path).as_posix()}"
        if expected not in sdist_names:
            errors.append(f"sdist is missing bundled skill file: {expected}")
    if any("/jdi-bridge/" in f"/{name}" for name in sdist_names):
        errors.append("sdist unexpectedly contains jdi-bridge sources")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    errors = validate_distributions(args.wheel, args.sdist, repo_root=repo_root)
    if errors:
        for error in errors:
            print(f"Distribution validation failed: {error}", file=sys.stderr)
        return 1

    print("Validated Python distribution contents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
