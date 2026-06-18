#!/usr/bin/env python3
"""Validate bundled Agent Skills against the project conventions."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?$")
REFERENCE_RE = re.compile(r"(?<![\w/])references/[A-Za-z0-9_.-]+\.md")


class SkillValidationError(Exception):
    """Raised when a skill cannot be parsed."""


def _clean_yaml_value(value: str) -> str:
    value = value.strip()
    if value in {"", "|", ">", "|-", ">-", "|+", ">+"}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _split_frontmatter(path: Path) -> tuple[list[str], list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillValidationError("SKILL.md must start with YAML frontmatter delimiter '---'")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index], lines[index + 1 :]

    raise SkillValidationError("SKILL.md frontmatter is missing closing delimiter '---'")


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    errors: list[str] = []
    current_field: str | None = None

    for line_number, raw_line in enumerate(lines, start=2):
        if not raw_line.strip():
            continue

        if raw_line[0].isspace():
            if current_field is None:
                errors.append(f"frontmatter line {line_number}: continuation without a field")
                continue
            fields[current_field] = f"{fields[current_field]} {raw_line.strip()}".strip()
            continue

        match = FIELD_RE.match(raw_line)
        if match is None:
            errors.append(f"frontmatter line {line_number}: expected 'field: value'")
            current_field = None
            continue

        key = match.group(1)
        value = _clean_yaml_value(match.group(2) or "")
        if key in fields:
            errors.append(f"frontmatter line {line_number}: duplicate field '{key}'")
        fields[key] = value
        current_field = key

    return fields, errors


def _check_fenced_code(path: Path, text: str, errors: list[str]) -> None:
    fence_count = sum(1 for line in text.splitlines() if line.lstrip().startswith("```"))
    if fence_count % 2 != 0:
        errors.append(f"{path}: unbalanced fenced code blocks")


def _check_reference_paths(skill_dir: Path, path: Path, text: str, errors: list[str]) -> None:
    for reference in sorted(set(REFERENCE_RE.findall(text))):
        if not (skill_dir / reference).is_file():
            errors.append(f"{path}: missing referenced file '{reference}'")


def _validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill_dir}: missing SKILL.md"]

    try:
        frontmatter_lines, body_lines = _split_frontmatter(skill_file)
    except SkillValidationError as exc:
        return [f"{skill_file}: {exc}"]

    fields, frontmatter_errors = _parse_frontmatter(frontmatter_lines)
    errors.extend(f"{skill_file}: {message}" for message in frontmatter_errors)

    unknown_fields = sorted(set(fields) - ALLOWED_FRONTMATTER_FIELDS)
    if unknown_fields:
        errors.append(f"{skill_file}: unsupported frontmatter fields: {', '.join(unknown_fields)}")

    name = fields.get("name", "")
    if not name:
        errors.append(f"{skill_file}: missing required frontmatter field 'name'")
    elif len(name) > 64 or not NAME_RE.fullmatch(name):
        errors.append(f"{skill_file}: invalid skill name '{name}'")
    elif name != skill_dir.name:
        errors.append(f"{skill_file}: name '{name}' must match folder '{skill_dir.name}'")

    description = fields.get("description", "")
    if not description:
        errors.append(f"{skill_file}: missing required frontmatter field 'description'")
    elif len(description) > 1024:
        errors.append(f"{skill_file}: description exceeds 1024 characters")
    elif "use when" not in description.lower():
        errors.append(f"{skill_file}: description should include concrete 'Use when' triggers")

    body_text = "\n".join(body_lines).strip()
    if not body_text:
        errors.append(f"{skill_file}: body must contain instructions")
    if len(body_lines) > 500:
        errors.append(f"{skill_file}: SKILL.md body should stay under 500 lines")

    skill_text = skill_file.read_text(encoding="utf-8")
    _check_fenced_code(skill_file, skill_text, errors)
    _check_reference_paths(skill_dir, skill_file, skill_text, errors)

    reference_dir = skill_dir / "references"
    if reference_dir.is_dir():
        for reference_file in sorted(reference_dir.glob("*.md")):
            reference_text = reference_file.read_text(encoding="utf-8")
            reference_lines = reference_text.splitlines()
            _check_fenced_code(reference_file, reference_text, errors)
            _check_reference_paths(skill_dir, reference_file, reference_text, errors)

            first_lines = "\n".join(reference_lines[:8])
            if "Read this file when" not in first_lines:
                errors.append(f"{reference_file}: missing top-of-file read trigger")
            if len(reference_lines) > 100 and "## Contents" not in "\n".join(reference_lines[:40]):
                errors.append(f"{reference_file}: references over 100 lines need a top-level Contents")
            if "TODO" in reference_text or "FIXME" in reference_text:
                errors.append(f"{reference_file}: contains TODO/FIXME markers")

    return errors


def validate_skills(skills_root: Path) -> list[str]:
    if not skills_root.is_dir():
        return [f"{skills_root}: skills root does not exist"]

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not skill_dirs:
        return [f"{skills_root}: no skill directories found"]

    errors: list[str] = []
    for skill_dir in skill_dirs:
        errors.extend(_validate_skill(skill_dir))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate bundled Agent Skills.")
    parser.add_argument(
        "skills_root",
        nargs="?",
        default="skills",
        type=Path,
        help="Directory containing skill folders (default: skills)",
    )
    args = parser.parse_args()

    errors = validate_skills(args.skills_root)
    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated Agent Skills in {args.skills_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
