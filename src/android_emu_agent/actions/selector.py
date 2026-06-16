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


SUPPORTED_SELECTOR_SYNTAX = [
    "^ref",
    "text:<value>",
    "text-contains:<value>",
    "text-matches:<regex>",
    "id:<resource_id>",
    "id-matches:<regex>",
    "desc:<value>",
    "desc-contains:<value>",
    "desc-matches:<regex>",
    "class:<class_name>",
    "coords:x,y",
]

SUPPORTED_SELECTOR_KEYS = [
    "text",
    "textContains",
    "textMatches",
    "resourceId",
    "resourceIdMatches",
    "description",
    "descriptionContains",
    "descriptionMatches",
    "className",
]


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
class TextContainsSelector(Selector):
    """Selector for text-contains: syntax."""

    text: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 textContains selector kwargs."""
        return {"textContains": self.text}


@dataclass
class TextMatchesSelector(Selector):
    """Selector for text-matches: syntax."""

    pattern: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 textMatches selector kwargs."""
        return {"textMatches": self.pattern}


@dataclass
class ResourceIdSelector(Selector):
    """Selector for id: syntax."""

    resource_id: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 resourceId selector kwargs."""
        return {"resourceId": self.resource_id}


@dataclass
class ResourceIdMatchesSelector(Selector):
    """Selector for id-matches: syntax."""

    pattern: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 resourceIdMatches selector kwargs."""
        return {"resourceIdMatches": self.pattern}


@dataclass
class DescSelector(Selector):
    """Selector for desc: syntax."""

    desc: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 description selector kwargs."""
        return {"description": self.desc}


@dataclass
class DescContainsSelector(Selector):
    """Selector for desc-contains: syntax."""

    desc: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 descriptionContains selector kwargs."""
        return {"descriptionContains": self.desc}


@dataclass
class DescMatchesSelector(Selector):
    """Selector for desc-matches: syntax."""

    pattern: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 descriptionMatches selector kwargs."""
        return {"descriptionMatches": self.pattern}


@dataclass
class ClassSelector(Selector):
    """Selector for class: syntax."""

    class_name: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 className selector kwargs."""
        return {"className": self.class_name}


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
    - text-contains:value - TextContainsSelector
    - text-matches:regex - TextMatchesSelector
    - id:resource_id - ResourceIdSelector
    - id-matches:regex - ResourceIdMatchesSelector
    - desc:"..." or desc:'...' or desc:value - DescSelector
    - desc-contains:value - DescContainsSelector
    - desc-matches:regex - DescMatchesSelector
    - class:class_name - ClassSelector
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
        return TextSelector(text=_selector_value(target, "text:"))

    if target.startswith("text-contains:"):
        return TextContainsSelector(text=_selector_value(target, "text-contains:"))

    if target.startswith("text-matches:"):
        return TextMatchesSelector(pattern=_selector_value(target, "text-matches:"))

    if target.startswith("id:"):
        return ResourceIdSelector(resource_id=_selector_value(target, "id:"))

    if target.startswith("id-matches:"):
        return ResourceIdMatchesSelector(pattern=_selector_value(target, "id-matches:"))

    if target.startswith("desc:"):
        return DescSelector(desc=_selector_value(target, "desc:"))

    if target.startswith("desc-contains:"):
        return DescContainsSelector(desc=_selector_value(target, "desc-contains:"))

    if target.startswith("desc-matches:"):
        return DescMatchesSelector(pattern=_selector_value(target, "desc-matches:"))

    if target.startswith("class:"):
        return ClassSelector(class_name=_selector_value(target, "class:"))

    if target.startswith("coords:"):
        try:
            coords_str = target[7:]
            x_str, y_str = coords_str.split(",")
            return CoordsSelector(x=int(x_str), y=int(y_str))
        except (ValueError, IndexError):
            raise invalid_selector_error(target) from None

    raise invalid_selector_error(target)


def _selector_value(target: str, prefix: str) -> str:
    value = target[len(prefix) :].strip().strip('"').strip("'")
    if not value:
        raise invalid_selector_error(target)
    return value
