"""Selector types and parser for escape hatch actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from android_emu_agent.errors import invalid_selector_error


class Selector(ABC):
    """Base class for element selectors."""

    @abstractmethod
    def to_u2_kwargs(self) -> dict[str, Any]:
        """Convert to uiautomator2 selector kwargs."""
        pass


@dataclass
class RefSelector(Selector):
    """Selector for ^ref syntax."""

    ref: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """RefSelector returns empty kwargs (resolved elsewhere)."""
        return {}


@dataclass
class TextSelector(Selector):
    """Selector for text: syntax."""

    text: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 text selector kwargs."""
        return {"text": self.text}


@dataclass
class ResourceIdSelector(Selector):
    """Selector for id: syntax."""

    resource_id: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 resourceId selector kwargs."""
        return {"resourceId": self.resource_id}


@dataclass
class DescSelector(Selector):
    """Selector for desc: syntax."""

    desc: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 description selector kwargs."""
        return {"description": self.desc}


@dataclass
class CoordsSelector(Selector):
    """Selector for coords: syntax."""

    x: int
    y: int

    def to_u2_kwargs(self) -> dict[str, Any]:
        """CoordsSelector returns empty kwargs (handled specially)."""
        return {}


def parse_selector(target: str) -> Selector:
    """
    Parse escape hatch selector or ref.

    Supported formats:
    - ^ref (e.g., ^a1, ^b5) - RefSelector
    - text:"..." or text:'...' or text:value - TextSelector
    - id:resource_id - ResourceIdSelector
    - desc:"..." or desc:'...' or desc:value - DescSelector
    - coords:x,y - CoordsSelector

    Args:
        target: The selector string to parse.

    Returns:
        Parsed Selector instance.

    Raises:
        AgentError: If selector format is invalid (ERR_INVALID_SELECTOR).
    """
    if not target:
        raise invalid_selector_error(target)

    if target.startswith("^"):
        return RefSelector(ref=target)

    if target.startswith("text:"):
        text = target[5:].strip('"').strip("'")
        return TextSelector(text=text)

    if target.startswith("id:"):
        return ResourceIdSelector(resource_id=target[3:])

    if target.startswith("desc:"):
        desc = target[5:].strip('"').strip("'")
        return DescSelector(desc=desc)

    if target.startswith("coords:"):
        try:
            coords_str = target[7:]
            x_str, y_str = coords_str.split(",")
            return CoordsSelector(x=int(x_str), y=int(y_str))
        except (ValueError, IndexError):
            raise invalid_selector_error(target) from None

    raise invalid_selector_error(target)
