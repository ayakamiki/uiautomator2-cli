"""Hierarchy capture and rendering services."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

from u2cli.backends.base import AutomationBackend


@dataclass(frozen=True)
class HierarchyDump:
    """Unified hierarchy payload exposed to command handlers."""

    content: str
    raw_xml: str
    output_format: str
    platform: str
    backend_name: str


class HierarchyService(Protocol):
    """Render backend hierarchy data into a stable command-facing shape."""

    def dump(self, *, compressed: bool = False, max_depth: int | None = None, raw: bool = False) -> HierarchyDump:
        """Capture hierarchy data and render it for CLI output."""


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _bounds_area(bounds_str: str) -> int:
    match = _BOUNDS_RE.fullmatch(bounds_str)
    if not match:
        return 0
    x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    return max(0, x2 - x1) * max(0, y2 - y1)


def _short_class(class_name: str) -> str:
    return class_name.rpartition(".")[2] if class_name else class_name


def _is_invisible(node: ET.Element) -> bool:
    if node.get("displayed") == "false":
        return True
    bounds = node.get("bounds", "")
    return bool(bounds) and _bounds_area(bounds) == 0


def _has_content(node: ET.Element) -> bool:
    return bool(
        node.get("text", "").strip()
        or node.get("content-desc", "").strip()
        or node.get("resource-id", "").strip()
    )


def _is_interactive(node: ET.Element) -> bool:
    return node.get("clickable") == "true" or node.get("scrollable") == "true"


def _render_node(node: ET.Element, lines: list[str], depth: int) -> None:
    if _is_invisible(node):
        return

    children = list(node)

    if (
        node.tag != "hierarchy"
        and not _has_content(node)
        and not _is_interactive(node)
        and len(children) == 1
    ):
        _render_node(children[0], lines, depth)
        return

    parts: list[str] = []

    class_name = node.get("class", node.tag)
    if class_name and class_name != "hierarchy":
        parts.append(_short_class(class_name))

    text = node.get("text", "").strip()
    if text:
        parts.append(f'"{text}"')

    desc = node.get("content-desc", "").strip()
    if desc and desc != text:
        parts.append(f'desc="{desc}"')

    resource_id = node.get("resource-id", "").strip()
    if resource_id:
        parts.append(f"#{resource_id}")

    bounds = node.get("bounds", "")
    if bounds:
        match = _BOUNDS_RE.fullmatch(bounds)
        if match:
            parts.append(f"[{match.group(1)},{match.group(2)},{match.group(3)},{match.group(4)}]")

    flags = []
    if node.get("clickable") == "true":
        flags.append("click")
    if node.get("scrollable") == "true":
        flags.append("scroll")
    if node.get("checked") == "true":
        flags.append("checked")
    if node.get("focused") == "true":
        flags.append("focused")
    if node.get("selected") == "true":
        flags.append("selected")
    if node.get("enabled") == "false":
        flags.append("disabled")
    if flags:
        parts.append(" ".join(flags))

    if parts:
        lines.append("  " * depth + " ".join(parts))
        child_depth = depth + 1
    else:
        child_depth = depth

    for child in children:
        _render_node(child, lines, child_depth)


def hierarchy_to_text(xml_str: str) -> str:
    """Convert raw hierarchy XML to a compact indented text tree."""

    root = ET.fromstring(xml_str)
    lines: list[str] = []
    _render_node(root, lines, 0)
    return "\n".join(lines)


class BackendHierarchyService:
    """Hierarchy service backed by an automation backend."""

    def __init__(self, backend: AutomationBackend) -> None:
        self._backend = backend

    def dump(self, *, compressed: bool = False, max_depth: int | None = None, raw: bool = False) -> HierarchyDump:
        raw_xml = self._backend.dump_hierarchy_xml(compressed=compressed, max_depth=max_depth)
        output_format = "xml" if raw else "text"
        content = raw_xml if raw else hierarchy_to_text(raw_xml)
        return HierarchyDump(
            content=content,
            raw_xml=raw_xml,
            output_format=output_format,
            platform=self._backend.platform,
            backend_name=self._backend.backend_name,
        )


def create_hierarchy_service(backend: AutomationBackend) -> HierarchyService:
    """Create the hierarchy service for a backend."""

    return BackendHierarchyService(backend)