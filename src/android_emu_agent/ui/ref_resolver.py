"""Ref resolver - Locator bundles, drift detection, stale ref handling."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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
    role: str = "element"
    state: dict[str, bool] = field(default_factory=dict)
    label: str | None = None
    ancestry_path: str = ""  # Path from root like "FrameLayout/LinearLayout/Button"
    element_hash: str = ""  # Stable hash for identification
    selector_chain: list[dict[str, str]] = field(default_factory=list)

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
            "role": self.role,
            "state": self.state,
            "label": self.label,
            "ancestry_path": self.ancestry_path,
            "element_hash": self.element_hash,
            "selector_chain": self.selector_chain,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], generation: int | None = None) -> LocatorBundle:
        """Hydrate a bundle from persisted ref payload."""
        resolved_generation = generation if generation is not None else payload.get("generation", 0)
        bundle = cls(
            ref=payload["ref"],
            generation=resolved_generation,
            resource_id=payload.get("resource_id"),
            content_desc=payload.get("content_desc"),
            text=payload.get("text"),
            class_name=payload.get("class_name") or payload.get("class", ""),
            bounds=payload.get("bounds", [0, 0, 0, 0]),
            ancestry_hash=payload.get("ancestry_hash") or "",
            index=payload.get("index", 0),
            role=payload.get("role", "element"),
            state=dict(payload.get("state", {})),
            label=payload.get("label"),
            ancestry_path=payload.get("ancestry_path", ""),
            element_hash=payload.get("element_hash", ""),
            selector_chain=list(payload.get("selector_chain") or []),
        )
        if not bundle.ancestry_hash:
            bundle.ancestry_hash = RefResolver.compute_ancestry_hash(bundle)
        if not bundle.selector_chain:
            bundle.selector_chain = RefResolver.build_selector_chain(bundle)
        return bundle


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
        for elem in elements:
            bundle = LocatorBundle.from_dict(
                {
                    **elem,
                    "generation": generation,
                    "ancestry_hash": elem.get("ancestry_hash"),
                    "selector_chain": elem.get("selector_chain"),
                },
                generation=generation,
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

    def get_generation_refs(self, session_id: str, generation: int) -> list[LocatorBundle]:
        """Return all refs for a specific generation."""
        return list(self._ref_maps.get(session_id, {}).get(generation, {}).values())

    def rebind_locator(
        self,
        session_id: str,
        locator: LocatorBundle,
        current_generation: int,
    ) -> LocatorBundle | None:
        """Rebind a stale locator against the latest stored generation."""
        candidates = self.get_generation_refs(session_id, current_generation)
        if not candidates:
            return None
        return self.match_locator(locator, candidates)

    @staticmethod
    def compute_ancestry_hash(locator: LocatorBundle) -> str:
        """Compute a hash of stable ancestry-aware locator features."""
        key_parts = [
            RefResolver.normalize_resource_id(locator.resource_id),
            RefResolver.normalize_text(locator.content_desc),
            RefResolver.normalize_text(locator.text),
            RefResolver.normalize_text(locator.label),
            locator.class_name,
            locator.role,
            RefResolver.state_signature(locator.state),
            locator.ancestry_path,
        ]
        key = "|".join(key_parts)
        return hashlib.md5(key.encode()).hexdigest()[:8]

    @staticmethod
    def build_selector_chain(locator: LocatorBundle) -> list[dict[str, str]]:
        """Build a narrow selector chain for stale-ref rebinding."""
        chain: list[dict[str, str]] = []
        if locator.resource_id:
            chain.append({"kind": "resource_id", "value": locator.resource_id})
            normalized_id = RefResolver.normalize_resource_id(locator.resource_id)
            if normalized_id and normalized_id != locator.resource_id:
                chain.append({"kind": "normalized_resource_id", "value": normalized_id})
        if locator.content_desc:
            chain.append({"kind": "content_desc", "value": locator.content_desc})
        if locator.text:
            chain.append({"kind": "text", "value": locator.text})
        if locator.label and locator.label not in {locator.text, locator.content_desc}:
            chain.append({"kind": "label", "value": locator.label})
        if locator.role:
            chain.append({"kind": "role", "value": locator.role})
        signature = RefResolver.state_signature(locator.state)
        if signature:
            chain.append({"kind": "state_signature", "value": signature})
        if locator.element_hash:
            chain.append({"kind": "element_hash", "value": locator.element_hash})
        if locator.ancestry_path:
            chain.append({"kind": "ancestry_path", "value": locator.ancestry_path})
        chain.append({"kind": "class_name", "value": locator.class_name})
        chain.append({"kind": "class_index", "value": f"{locator.class_name}#{locator.index}"})
        return chain

    @staticmethod
    def normalize_resource_id(resource_id: str | None) -> str:
        """Normalize classic view IDs and Compose test tags."""
        if not resource_id:
            return ""
        if ":id/" in resource_id:
            return resource_id.split(":id/", 1)[1]
        return resource_id

    @staticmethod
    def normalize_text(value: str | None) -> str:
        """Normalize framework-emitted labels for matching."""
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def state_signature(state: dict[str, bool]) -> str:
        """Summarize semantically important node flags."""
        return "|".join(
            key
            for key in ("clickable", "editable", "checked", "scrollable")
            if state.get(key, False)
        )

    def match_locator(
        self,
        locator: LocatorBundle,
        candidates: list[LocatorBundle],
    ) -> LocatorBundle | None:
        """Resolve a stale locator against a newer generation."""
        if not candidates:
            return None

        filtered = candidates
        narrowed = False
        for step in locator.selector_chain or self.build_selector_chain(locator):
            matches = [candidate for candidate in filtered if self._matches_step(candidate, step)]
            if len(matches) == 1:
                return matches[0]
            if matches:
                filtered = matches
                narrowed = True

        if narrowed and len(filtered) == 1:
            return filtered[0]

        ranked = sorted(
            ((self._score_candidate(locator, candidate), candidate) for candidate in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 35:
            return None
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None
        return ranked[0][1]

    def _matches_step(self, candidate: LocatorBundle, step: dict[str, str]) -> bool:
        """Check whether a candidate satisfies a selector-chain step."""
        kind = step.get("kind")
        value = step.get("value")
        if not kind or value is None:
            return False
        if kind == "resource_id":
            return candidate.resource_id == value
        if kind == "normalized_resource_id":
            return self.normalize_resource_id(candidate.resource_id) == value
        if kind == "content_desc":
            return self.normalize_text(candidate.content_desc) == self.normalize_text(value)
        if kind == "text":
            return self.normalize_text(candidate.text) == self.normalize_text(value)
        if kind == "label":
            return self.normalize_text(candidate.label) == self.normalize_text(value)
        if kind == "role":
            return candidate.role == value
        if kind == "state_signature":
            return self.state_signature(candidate.state) == value
        if kind == "element_hash":
            return candidate.element_hash == value
        if kind == "ancestry_path":
            return candidate.ancestry_path == value
        if kind == "class_name":
            return candidate.class_name == value
        if kind == "class_index":
            return f"{candidate.class_name}#{candidate.index}" == value
        return False

    def _score_candidate(self, locator: LocatorBundle, candidate: LocatorBundle) -> int:
        """Score a candidate when the selector chain is not uniquely identifying."""
        score = 0
        if locator.resource_id and self.normalize_resource_id(locator.resource_id) == self.normalize_resource_id(candidate.resource_id):
            score += 80
        if self.normalize_text(locator.content_desc) and self.normalize_text(locator.content_desc) == self.normalize_text(candidate.content_desc):
            score += 50
        if self.normalize_text(locator.text) and self.normalize_text(locator.text) == self.normalize_text(candidate.text):
            score += 40
        if self.normalize_text(locator.label) and self.normalize_text(locator.label) == self.normalize_text(candidate.label):
            score += 30
        if locator.role == candidate.role:
            score += 20
        if self.state_signature(locator.state) and self.state_signature(locator.state) == self.state_signature(candidate.state):
            score += 15
        if locator.element_hash and locator.element_hash == candidate.element_hash:
            score += 25
        if locator.ancestry_path and locator.ancestry_path == candidate.ancestry_path:
            score += 20
        if locator.class_name == candidate.class_name:
            score += 10

        old_center_x = (locator.bounds[0] + locator.bounds[2]) // 2
        old_center_y = (locator.bounds[1] + locator.bounds[3]) // 2
        new_center_x = (candidate.bounds[0] + candidate.bounds[2]) // 2
        new_center_y = (candidate.bounds[1] + candidate.bounds[3]) // 2
        distance = abs(old_center_x - new_center_x) + abs(old_center_y - new_center_y)
        score += max(0, 15 - min(distance // 50, 15))
        return score

    def _cleanup_old_generations(self, session_id: str, current: int) -> None:
        """Remove generations older than current - 2."""
        if session_id not in self._ref_maps:
            return

        session_refs = self._ref_maps[session_id]
        old_gens = [g for g in session_refs if g < current - 2]
        for gen in old_gens:
            del session_refs[gen]
            logger.debug("generation_cleaned", session_id=session_id, generation=gen)
