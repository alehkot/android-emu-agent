"""UI Snapshotter - Actionable filtering and ref metadata extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import md5
from typing import TYPE_CHECKING, Any

import structlog
from lxml import etree

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Warning threshold for snapshot size (20KB)
SNAPSHOT_SIZE_WARNING_BYTES = 20480

STRUCTURAL_CLASS_MARKERS = (
    "framelayout",
    "linearlayout",
    "relativelayout",
    "constraintlayout",
    "coordinatorlayout",
    "drawerlayout",
    "layout",
    "viewgroup",
    "fragmentcontainerview",
)


@dataclass
class ElementNode:
    """Represents an actionable UI element."""

    ref: str
    role: str
    label: str | None
    resource_id: str | None
    class_name: str
    bounds: list[int]
    state: dict[str, bool]
    content_desc: str | None = None
    text: str | None = None
    index: int = 0
    ancestry_path: str = ""
    element_hash: str = ""
    selector_chain: list[dict[str, str]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """Convert to public snapshot schema."""
        return {
            "ref": self.ref,
            "role": self.role,
            "label": self.label,
            "resource_id": self.resource_id,
            "class": self.class_name,
            "bounds": self.bounds,
            "state": self.state,
            "content_desc": self.content_desc,
            "text": self.text,
        }

    def to_ref_dict(self, generation: int) -> dict[str, Any]:
        """Convert to richer ref metadata for storage and rebinding."""
        return {
            **self.to_public_dict(),
            "generation": generation,
            "index": self.index,
            "ancestry_path": self.ancestry_path,
            "element_hash": self.element_hash,
            "selector_chain": self.selector_chain,
        }


@dataclass
class Snapshot:
    """Complete UI snapshot with context and elements."""

    schema_version: int
    session_id: str
    generation: int
    timestamp_ms: int
    device: dict[str, Any]
    context: dict[str, Any]
    elements: list[ElementNode]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "generation": self.generation,
            "timestamp_ms": self.timestamp_ms,
            "device": self.device,
            "context": self.context,
            "elements": [e.to_public_dict() for e in self.elements],
        }

        # Check size and add warning if needed
        size_bytes = len(json.dumps(result).encode())
        if size_bytes > SNAPSHOT_SIZE_WARNING_BYTES:
            result["warnings"] = [
                f"Snapshot size {size_bytes // 1024}KB exceeds 20KB target. "
                "Consider filtering or using a simpler screen."
            ]

        return result

    def ref_payloads(self) -> list[dict[str, Any]]:
        """Return rich ref payloads for persistence and rebinding."""
        return [element.to_ref_dict(self.generation) for element in self.elements]


class UISnapshotter:
    """Generates actionable UI snapshots from device hierarchy."""

    def __init__(self) -> None:
        self._ref_counter = 0

    def parse_hierarchy(
        self,
        xml_content: bytes,
        session_id: str,
        generation: int,
        device_info: dict[str, Any],
        context_info: dict[str, Any],
        interactive_only: bool = True,
    ) -> Snapshot:
        """Parse XML hierarchy and extract elements."""
        import time

        start = time.time()
        tree = etree.fromstring(xml_content)
        elements = self._extract_elements(tree, interactive_only=interactive_only)
        elapsed = (time.time() - start) * 1000

        logger.info(
            "hierarchy_parsed",
            element_count=len(elements),
            elapsed_ms=round(elapsed, 2),
        )

        return Snapshot(
            schema_version=1,
            session_id=session_id,
            generation=generation,
            timestamp_ms=int(time.time() * 1000),
            device=device_info,
            context=context_info,
            elements=elements,
        )

    def _extract_elements(
        self,
        tree: etree._Element,
        *,
        interactive_only: bool,
    ) -> list[ElementNode]:
        """Extract elements using traversal and compact actionable rules."""
        elements: list[ElementNode] = []
        self._ref_counter = 0

        self._collect_elements(
            node=tree,
            parent_path=[],
            interactive_only=interactive_only,
            interactive_ancestor=False,
            sibling_index=0,
            elements=elements,
        )

        return elements

    def _collect_elements(
        self,
        *,
        node: etree._Element,
        parent_path: list[str],
        interactive_only: bool,
        interactive_ancestor: bool,
        sibling_index: int,
        elements: list[ElementNode],
    ) -> None:
        """Walk the hierarchy and collect actionable elements."""
        class_name = node.get("class", node.tag)
        ancestry_path = "/".join([*parent_path, class_name])
        interactive = self._is_interactive(node)
        include = self._should_include(
            node=node,
            interactive_only=interactive_only,
            interactive=interactive,
            interactive_ancestor=interactive_ancestor,
        )

        if include:
            element = self._node_to_element(
                node,
                sibling_index=sibling_index,
                ancestry_path=ancestry_path,
                proxy_label=self._proxy_label(node) if interactive_only else None,
            )
            if element:
                elements.append(element)

        child_nodes = [child for child in node if isinstance(child, etree._Element)]
        next_interactive_ancestor = interactive_ancestor or interactive
        for index, child in enumerate(child_nodes):
            self._collect_elements(
                node=child,
                parent_path=[*parent_path, class_name],
                interactive_only=interactive_only,
                interactive_ancestor=next_interactive_ancestor,
                sibling_index=index,
                elements=elements,
            )

    def _node_to_element(
        self,
        node: etree._Element,
        *,
        sibling_index: int,
        ancestry_path: str,
        proxy_label: str | None = None,
    ) -> ElementNode | None:
        """Convert XML node to ElementNode."""
        self._ref_counter += 1
        ref = f"^a{self._ref_counter}"

        # Parse bounds "[left,top][right,bottom]"
        bounds_str = node.get("bounds", "[0,0][0,0]")
        bounds = self._parse_bounds(bounds_str)

        # Determine role from class name
        class_name = node.get("class", "")
        role = self._infer_role(class_name, node)

        # Prefer a proxy label when a clickable container needs descendant text to be discoverable.
        content_desc = node.get("content-desc")
        text = node.get("text")
        label = content_desc or text or proxy_label or None
        state = {
            "clickable": node.get("clickable") == "true",
            "focusable": node.get("focusable") == "true",
            "focused": node.get("focused") == "true",
            "enabled": node.get("enabled") != "false",
            "checked": node.get("checked") == "true",
            "selected": node.get("selected") == "true",
            "scrollable": node.get("scrollable") == "true",
            "editable": node.get("editable") == "true",
        }
        element_hash = self._compute_element_hash(
            class_name=class_name,
            resource_id=node.get("resource-id"),
            content_desc=content_desc,
            text=text,
            label=label,
            ancestry_path=ancestry_path,
        )

        return ElementNode(
            ref=ref,
            role=role,
            label=label,
            resource_id=node.get("resource-id"),
            class_name=class_name,
            bounds=bounds,
            content_desc=content_desc or None,
            text=text or None,
            state=state,
            index=sibling_index,
            ancestry_path=ancestry_path,
            element_hash=element_hash,
            selector_chain=self._build_selector_chain(
                resource_id=node.get("resource-id"),
                content_desc=content_desc or None,
                text=text or None,
                label=label,
                role=role,
                state=state,
                class_name=class_name,
                ancestry_path=ancestry_path,
                element_hash=element_hash,
                index=sibling_index,
            ),
        )

    def _parse_bounds(self, bounds_str: str) -> list[int]:
        """Parse bounds string '[left,top][right,bottom]' to list."""
        try:
            # Remove brackets and split
            clean = bounds_str.replace("][", ",").strip("[]")
            parts = clean.split(",")
            return [int(p) for p in parts[:4]]
        except (ValueError, IndexError):
            return [0, 0, 0, 0]

    def _infer_role(self, class_name: str, node: etree._Element) -> str:
        """Infer semantic role from class name."""
        class_lower = class_name.lower()

        if "button" in class_lower:
            return "button"
        if "edittext" in class_lower:
            return "textfield"
        if "textview" in class_lower:
            return "text"
        if "imageview" in class_lower:
            return "image"
        if "checkbox" in class_lower:
            return "checkbox"
        if "switch" in class_lower:
            return "switch"
        if "radiobutton" in class_lower:
            return "radio"
        if "recyclerview" in class_lower or "listview" in class_lower:
            return "list"
        if "scrollview" in class_lower:
            return "scrollable"

        # Fallback based on state
        if node.get("checkable") == "true":
            return "checkbox"
        if node.get("scrollable") == "true":
            return "scrollable"
        if node.get("clickable") == "true":
            return "clickable"
        if node.get("editable") == "true":
            return "textfield"

        return "element"

    def _should_include(
        self,
        *,
        node: etree._Element,
        interactive_only: bool,
        interactive: bool,
        interactive_ancestor: bool,
    ) -> bool:
        """Apply compact actionable filtering while preserving full snapshots."""
        if node.tag == "hierarchy":
            return False

        if not self._has_visible_bounds(node):
            return False

        if not interactive_only:
            return True

        if interactive:
            return True

        if interactive_ancestor:
            return False

        label = self._own_label(node)
        if not label:
            return False

        return not self._is_structural(node)

    def _is_interactive(self, node: etree._Element) -> bool:
        """Return whether the node is a meaningful interaction target."""
        interactive_attrs = (
            "clickable",
            "focusable",
            "scrollable",
            "checkable",
            "editable",
            "long-clickable",
        )
        return any(node.get(attr) == "true" for attr in interactive_attrs)

    def _is_structural(self, node: etree._Element) -> bool:
        """Return whether the node is likely layout-only noise."""
        class_name = node.get("class", "")
        class_lower = class_name.lower()
        return any(marker in class_lower for marker in STRUCTURAL_CLASS_MARKERS)

    def _has_visible_bounds(self, node: etree._Element) -> bool:
        """Filter out zero-sized or explicitly hidden nodes."""
        if node.get("visible-to-user") == "false":
            return False

        left, top, right, bottom = self._parse_bounds(node.get("bounds", "[0,0][0,0]"))
        return right > left and bottom > top

    def _own_label(self, node: etree._Element) -> str | None:
        """Return the node's direct accessible label."""
        content_desc = (node.get("content-desc") or "").strip()
        if content_desc:
            return content_desc
        text = (node.get("text") or "").strip()
        return text or None

    def _proxy_label(self, node: etree._Element) -> str | None:
        """Borrow useful descendant text for unlabeled interactive containers."""
        if self._own_label(node):
            return None

        descendants = [child for child in node.iterdescendants() if isinstance(child, etree._Element)]
        for descendant in descendants:
            if self._is_interactive(descendant):
                continue
            label = self._own_label(descendant)
            if label and not self._is_structural(descendant):
                return label

        for descendant in descendants:
            label = self._own_label(descendant)
            if label:
                return label

        return None

    def _compute_element_hash(
        self,
        *,
        class_name: str,
        resource_id: str | None,
        content_desc: str | None,
        text: str | None,
        label: str | None,
        ancestry_path: str,
    ) -> str:
        """Compute a stable hash for rebinding heuristics."""
        raw = "|".join(
            [
                self._normalize_resource_id(resource_id),
                content_desc or "",
                text or "",
                label or "",
                class_name,
                ancestry_path,
            ]
        )
        return md5(raw.encode()).hexdigest()[:12]

    def _build_selector_chain(
        self,
        *,
        resource_id: str | None,
        content_desc: str | None,
        text: str | None,
        label: str | None,
        role: str,
        state: dict[str, bool],
        class_name: str,
        ancestry_path: str,
        element_hash: str,
        index: int,
    ) -> list[dict[str, str]]:
        """Build a narrow selector chain for stale-ref rebinding."""
        chain: list[dict[str, str]] = []
        if resource_id:
            chain.append({"kind": "resource_id", "value": resource_id})
            normalized_id = self._normalize_resource_id(resource_id)
            if normalized_id and normalized_id != resource_id:
                chain.append({"kind": "normalized_resource_id", "value": normalized_id})
        if content_desc:
            chain.append({"kind": "content_desc", "value": content_desc})
        if text:
            chain.append({"kind": "text", "value": text})
        if label and label not in {text, content_desc}:
            chain.append({"kind": "label", "value": label})
        if role:
            chain.append({"kind": "role", "value": role})
        signature = self._state_signature(state)
        if signature:
            chain.append({"kind": "state_signature", "value": signature})
        if element_hash:
            chain.append({"kind": "element_hash", "value": element_hash})
        if ancestry_path:
            chain.append({"kind": "ancestry_path", "value": ancestry_path})
        chain.append({"kind": "class_name", "value": class_name})
        chain.append({"kind": "class_index", "value": f"{class_name}#{index}"})
        return chain

    def _normalize_resource_id(self, resource_id: str | None) -> str:
        """Normalize framework-emitted resource identifiers and test tags."""
        if not resource_id:
            return ""
        if ":id/" in resource_id:
            return resource_id.split(":id/", 1)[1]
        return resource_id

    def _state_signature(self, state: dict[str, bool]) -> str:
        """Build a compact semantic-state signature for matching generic host views."""
        return "|".join(
            key
            for key in ("clickable", "editable", "checked", "scrollable")
            if state.get(key, False)
        )
