"""Optional visual grounding artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from android_emu_agent.errors import AgentError


class VisualGroundingManager:
    """Builds screenshot-to-ref grounding metadata without using vision models."""

    def __init__(self, output_dir: Path | None = None) -> None:
        default_dir = Path.home() / ".android-emu-agent" / "artifacts" / "visual"
        self.output_dir = output_dir or default_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_grounding(
        self,
        *,
        session_id: str,
        snapshot: dict[str, Any],
        screenshot_path: Path | None,
        refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create and persist visual grounding metadata for snapshot refs."""
        generation = self._generation(snapshot)
        selected_refs = refs or []
        elements = self._elements(snapshot, selected_refs)
        payload = {
            "status": "done",
            "session_id": session_id,
            "generation": generation,
            "vision_required": False,
            "coordinate_space": "screen_pixels",
            "screenshot_path": str(screenshot_path) if screenshot_path else None,
            "selected_refs": selected_refs,
            "elements": elements,
        }
        artifact_path = self._write_artifact(session_id, generation, payload)
        payload["path"] = str(artifact_path)
        return payload

    def _elements(self, snapshot: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
        raw_elements = snapshot.get("elements", [])
        if not isinstance(raw_elements, list):
            raise self._invalid_snapshot()

        requested = set(refs)
        elements: list[dict[str, Any]] = []
        found: set[str] = set()
        for item in raw_elements:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref")
            if not isinstance(ref, str):
                continue
            if requested and ref not in requested:
                continue
            found.add(ref)
            bounds = item.get("bounds")
            elements.append(
                {
                    "ref": ref,
                    "label": item.get("label"),
                    "text": item.get("text"),
                    "content_desc": item.get("content_desc"),
                    "resource_id": item.get("resource_id"),
                    "class": item.get("class"),
                    "role": item.get("role"),
                    "bounds": bounds,
                    "center": self._center(bounds),
                    "state": item.get("state"),
                }
            )

        missing = sorted(requested - found)
        if missing:
            raise AgentError(
                code="ERR_VISUAL_REF_NOT_FOUND",
                message=f"Refs not found in latest snapshot: {', '.join(missing)}",
                context={"refs": missing},
                remediation="Run 'ui snapshot' and use refs from the latest generation.",
            )
        return elements

    def _write_artifact(
        self,
        session_id: str,
        generation: int,
        payload: dict[str, Any],
    ) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"{session_id}_gen{generation}_{timestamp}_grounding.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    @staticmethod
    def _generation(snapshot: dict[str, Any]) -> int:
        generation = snapshot.get("generation")
        if isinstance(generation, int):
            return generation
        raise VisualGroundingManager._invalid_snapshot()

    @staticmethod
    def _center(bounds: Any) -> dict[str, int] | None:
        if not (
            isinstance(bounds, list)
            and len(bounds) == 4
            and all(isinstance(value, int) for value in bounds)
        ):
            return None
        left, top, right, bottom = bounds
        return {"x": (left + right) // 2, "y": (top + bottom) // 2}

    @staticmethod
    def _invalid_snapshot() -> AgentError:
        return AgentError(
            code="ERR_VISUAL_SNAPSHOT_INVALID",
            message="Latest snapshot is missing grounding metadata",
            context={},
            remediation="Run 'ui snapshot' before creating visual grounding.",
        )
