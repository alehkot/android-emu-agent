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
    "<selector> || <selector>",
    "^ref",
    "text:<value>",
    "text-contains:<value>",
    "text-matches:<regex>",
    "label:<value>",
    "id:<resource_id>",
    "id-matches:<regex>",
    "desc:<value>",
    "desc-contains:<value>",
    "desc-matches:<regex>",
    "class:<class_name>",
    "enabled:true|false",
    "clickable:true|false",
    "selected:true|false",
    "checked:true|false",
    "focused:true|false",
    "scrollable:true|false",
    "<selector> <state-filter:true|false>",
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
    "enabled",
    "clickable",
    "selected",
    "checked",
    "focused",
    "scrollable",
]

BOOLEAN_SELECTOR_KEYS = {
    "enabled": "enabled",
    "clickable": "clickable",
    "selected": "selected",
    "checked": "checked",
    "focused": "focused",
    "scrollable": "scrollable",
}


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
class LabelSelector(Selector):
    """Selector for label: syntax.

    On Android this maps to content-desc first. Use a fallback selector when the
    same user-facing label might be text in one build and content-desc in another.
    """

    label: str

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 description selector kwargs."""
        return {"description": self.label}


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


@dataclass
class U2Selector(Selector):
    """Compound uiautomator2 selector kwargs."""

    kwargs: dict[str, Any]

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Return uiautomator2 selector kwargs."""
        return dict(self.kwargs)


@dataclass
class FallbackSelector(Selector):
    """Ordered selector alternatives separated by ||."""

    options: list[Selector]

    def to_u2_kwargs(self) -> dict[str, Any]:
        """Fallback selectors are resolved by callers; expose the first option for compatibility."""
        return self.options[0].to_u2_kwargs() if self.options else {}


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

    fallback_parts = _split_fallbacks(target)
    if len(fallback_parts) > 1:
        if any(not part.strip() for part in fallback_parts):
            raise invalid_selector_error(target)
        return FallbackSelector(
            options=[parse_selector(part.strip()) for part in fallback_parts if part.strip()]
        )

    compound_parts = _split_compound(target)
    if len(compound_parts) > 1 and not _is_unquoted_value_selector(compound_parts):
        return U2Selector(kwargs=_compound_kwargs(compound_parts, target))

    if target.startswith("^"):
        return RefSelector(ref=target)

    if target.startswith("text:"):
        return TextSelector(text=_selector_value(target, "text:"))

    if target.startswith("text-contains:"):
        return TextContainsSelector(text=_selector_value(target, "text-contains:"))

    if target.startswith("text-matches:"):
        return TextMatchesSelector(pattern=_selector_value(target, "text-matches:"))

    if target.startswith("label:"):
        return LabelSelector(label=_selector_value(target, "label:"))

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

    for prefix in BOOLEAN_SELECTOR_KEYS:
        token_prefix = f"{prefix}:"
        if target.startswith(token_prefix):
            return U2Selector(kwargs={BOOLEAN_SELECTOR_KEYS[prefix]: _bool_value(target, token_prefix)})

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


def _split_fallbacks(target: str) -> list[str]:
    parts: list[str] = []
    start = 0
    in_single = False
    in_double = False
    escaped = False
    index = 0
    while index < len(target):
        char = target[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "|" and not in_single and not in_double and target[index : index + 2] == "||":
            parts.append(target[start:index])
            start = index + 2
            index += 1
        index += 1
    parts.append(target[start:])
    return parts


def _split_compound(target: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    for char in target:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == "'" and not in_double:
            current.append(char)
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            current.append(char)
            in_double = not in_double
            continue
        if char.isspace() and not in_single and not in_double:
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(char)
    if in_single or in_double:
        raise invalid_selector_error(target)
    if current:
        parts.append("".join(current))
    return parts


def _is_unquoted_value_selector(parts: list[str]) -> bool:
    if len(parts) <= 1:
        return False
    value_prefixes = (
        "text:",
        "text-contains:",
        "text-matches:",
        "label:",
        "desc:",
        "desc-contains:",
        "desc-matches:",
    )
    return parts[0].startswith(value_prefixes) and all(":" not in part for part in parts[1:])


def _compound_kwargs(parts: list[str], original: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for part in parts:
        selector = parse_selector(part)
        if isinstance(selector, (RefSelector, CoordsSelector, FallbackSelector)):
            raise invalid_selector_error(original)
        for key, value in selector.to_u2_kwargs().items():
            if key in kwargs:
                raise invalid_selector_error(original)
            kwargs[key] = value
    if not kwargs:
        raise invalid_selector_error(original)
    return kwargs


def _bool_value(target: str, prefix: str) -> bool:
    value = _selector_value(target, prefix).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise invalid_selector_error(target)
