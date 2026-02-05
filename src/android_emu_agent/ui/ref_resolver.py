"""Ref resolver - Locator bundles, drift detection, stale ref handling."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class LocatorBundle:
    """Bundle of locator strategies for an element."""

    ref: str
    generation: int
    resource_id: str | None
    content_desc: str | None
    text: str | None
    class_name: str
    bounds: list[int]
    ancestry_hash: str
    index: int  # Position among siblings
    ancestry_path: str = ""  # Path from root like "FrameLayout/LinearLayout/Button"
    element_hash: str = ""  # Stable hash for identification

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "ref": self.ref,
            "generation": self.generation,
            "resource_id": self.resource_id,
            "content_desc": self.content_desc,
            "text": self.text,
            "class_name": self.class_name,
            "bounds": self.bounds,
            "ancestry_hash": self.ancestry_hash,
            "index": self.index,
            "ancestry_path": self.ancestry_path,
            "element_hash": self.element_hash,
        }


class RefResolver:
    """Manages element refs and locator resolution."""

    def __init__(self) -> None:
        # session_id -> (generation -> (ref -> LocatorBundle))
        self._ref_maps: dict[str, dict[int, dict[str, LocatorBundle]]] = {}

    def store_refs(
        self,
        session_id: str,
        generation: int,
        elements: list[dict[str, Any]],
    ) -> None:
        """Store ref -> locator mappings for a snapshot generation."""
        if session_id not in self._ref_maps:
            self._ref_maps[session_id] = {}

        ref_map: dict[str, LocatorBundle] = {}
        for i, elem in enumerate(elements):
            bundle = LocatorBundle(
                ref=elem["ref"],
                generation=generation,
                resource_id=elem.get("resource_id"),
                content_desc=elem.get("content_desc"),
                text=elem.get("text"),
                class_name=elem.get("class", ""),
                bounds=elem.get("bounds", [0, 0, 0, 0]),
                ancestry_hash=self._compute_ancestry_hash(elem),
                index=i,
            )
            ref_map[elem["ref"]] = bundle

        self._ref_maps[session_id][generation] = ref_map
        logger.info(
            "refs_stored",
            session_id=session_id,
            generation=generation,
            count=len(ref_map),
        )

        # Cleanup old generations (keep last 3)
        self._cleanup_old_generations(session_id, generation)

    def resolve_ref(
        self,
        session_id: str,
        ref: str,
        current_generation: int,
    ) -> tuple[LocatorBundle | None, bool]:
        """
        Resolve a ref to its locator bundle.

        Returns:
            (bundle, is_stale): Bundle if found, and whether it's from an old generation.
        """
        if session_id not in self._ref_maps:
            return None, False

        session_refs = self._ref_maps[session_id]

        # Check current generation first
        if current_generation in session_refs and ref in session_refs[current_generation]:
            return session_refs[current_generation][ref], False

        # Check previous generations (stale but might work)
        for gen in sorted(session_refs.keys(), reverse=True):
            if gen < current_generation and ref in session_refs[gen]:
                logger.warning(
                    "stale_ref_resolved",
                    ref=ref,
                    ref_generation=gen,
                    current_generation=current_generation,
                )
                return session_refs[gen][ref], True

        return None, False

    def clear_session(self, session_id: str) -> None:
        """Clear all refs for a session."""
        if session_id in self._ref_maps:
            del self._ref_maps[session_id]
            logger.info("session_refs_cleared", session_id=session_id)

    def _compute_ancestry_hash(self, elem: dict[str, Any]) -> str:
        """Compute hash of element's identifying features."""
        key_parts = [
            elem.get("resource_id", ""),
            elem.get("class", ""),
            str(elem.get("bounds", [])),
        ]
        key = "|".join(key_parts)
        return hashlib.md5(key.encode()).hexdigest()[:8]

    def _cleanup_old_generations(self, session_id: str, current: int) -> None:
        """Remove generations older than current - 2."""
        if session_id not in self._ref_maps:
            return

        session_refs = self._ref_maps[session_id]
        old_gens = [g for g in session_refs if g < current - 2]
        for gen in old_gens:
            del session_refs[gen]
            logger.debug("generation_cleaned", session_id=session_id, generation=gen)
