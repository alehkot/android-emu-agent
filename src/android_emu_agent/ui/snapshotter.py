"""UI Snapshotter - Multi-source extraction, filtering, scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from lxml import etree

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Warning threshold for snapshot size (20KB)
SNAPSHOT_SIZE_WARNING_BYTES = 20480

# XPath for interactive elements only
INTERACTIVE_XPATH = (
    "//*["
    "@clickable='true' or "
    "@focusable='true' or "
    "@scrollable='true' or "
    "@checkable='true' or "
    "@editable='true' or "
    "string-length(@text)>0"
    "]"
)


@dataclass
class ElementNode:
    """Represents an interactive UI element."""

    ref: str
    role: str
    label: str | None
    resource_id: str | None
    class_name: str
    bounds: list[int]
    state: dict[str, bool]
    content_desc: str | None = None
    text: str | None = None


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
            "elements": [
                {
                    "ref": e.ref,
                    "role": e.role,
                    "label": e.label,
                    "resource_id": e.resource_id,
                    "class": e.class_name,
                    "bounds": e.bounds,
                    "state": e.state,
                    "content_desc": e.content_desc,
                    "text": e.text,
                }
                for e in self.elements
            ],
        }

        # Check size and add warning if needed
        size_bytes = len(json.dumps(result).encode())
        if size_bytes > SNAPSHOT_SIZE_WARNING_BYTES:
            result["warnings"] = [
                f"Snapshot size {size_bytes // 1024}KB exceeds 20KB target. "
                "Consider filtering or using a simpler screen."
            ]

        return result


class UISnapshotter:
    """Generates compact UI snapshots from device hierarchy."""

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
        """Extract elements using XPath."""
        elements: list[ElementNode] = []
        self._ref_counter = 0

        xpath = INTERACTIVE_XPATH if interactive_only else "//*"
        nodes = tree.xpath(xpath)
        if not isinstance(nodes, list):
            return elements
        for node in nodes:
            if not isinstance(node, etree._Element):
                continue
            element = self._node_to_element(node)
            if element:
                elements.append(element)

        return elements

    def _node_to_element(self, node: etree._Element) -> ElementNode | None:
        """Convert XML node to ElementNode."""
        self._ref_counter += 1
        ref = f"@a{self._ref_counter}"

        # Parse bounds "[left,top][right,bottom]"
        bounds_str = node.get("bounds", "[0,0][0,0]")
        bounds = self._parse_bounds(bounds_str)

        # Determine role from class name
        class_name = node.get("class", "")
        role = self._infer_role(class_name, node)

        # Get label (prefer content-desc, then text)
        content_desc = node.get("content-desc")
        text = node.get("text")
        label = content_desc or text or None

        return ElementNode(
            ref=ref,
            role=role,
            label=label,
            resource_id=node.get("resource-id"),
            class_name=class_name,
            bounds=bounds,
            content_desc=content_desc,
            text=text,
            state={
                "clickable": node.get("clickable") == "true",
                "focusable": node.get("focusable") == "true",
                "focused": node.get("focused") == "true",
                "enabled": node.get("enabled") == "true",
                "checked": node.get("checked") == "true",
                "selected": node.get("selected") == "true",
                "scrollable": node.get("scrollable") == "true",
                "editable": node.get("editable") == "true",
            },
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
        if node.get("clickable") == "true":
            return "clickable"
        if node.get("editable") == "true":
            return "textfield"

        return "element"
