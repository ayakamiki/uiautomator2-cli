"""Hierarchy capture and rendering services."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

from u2cli.backends.base import AutomationBackend


@dataclass(frozen=True)
class UiBounds:
    """Normalized rectangular bounds for a UI node."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def to_bracket_string(self) -> str:
        return f"[{self.left},{self.top},{self.right},{self.bottom}]"


@dataclass(frozen=True)
class UiNodeRef:
    """Stable reference to a normalized node inside a hierarchy snapshot."""

    path: tuple[int, ...]
    backend_path: str


@dataclass(frozen=True)
class UiNode:
    """Normalized UI node shared across Android and Harmony hierarchy snapshots."""

    ref: UiNodeRef
    tag: str
    class_name: str | None
    text: str
    content_desc: str
    resource_id: str
    package: str
    bounds: UiBounds | None
    clickable: bool
    scrollable: bool
    checkable: bool
    checked: bool
    enabled: bool
    focused: bool
    selected: bool
    visible: bool
    children: tuple[UiNode, ...]

    def primary_text(self) -> str:
        return self.text or self.content_desc or self.resource_id


@dataclass(frozen=True)
class HierarchySnapshot:
    """Captured normalized hierarchy tree with raw backend payload."""

    root: UiNode
    raw_xml: str
    platform: str
    backend_name: str


@dataclass(frozen=True)
class HierarchyDump:
    """Unified hierarchy payload exposed to command handlers."""

    content: str
    raw_xml: str
    output_format: str
    platform: str
    backend_name: str


class HierarchyService(Protocol):
    """Render backend hierarchy data into stable command-facing shapes."""

    def capture(self, *, compressed: bool = False, max_depth: int | None = None) -> HierarchySnapshot:
        """Capture and normalize hierarchy data from the backend."""

    def dump(self, *, compressed: bool = False, max_depth: int | None = None, raw: bool = False) -> HierarchyDump:
        """Capture hierarchy data and render it for CLI output."""

    def flatten(self, snapshot: HierarchySnapshot, *, include_invisible: bool = False) -> list[UiNode]:
        """Flatten a normalized hierarchy snapshot into document order."""

    def resolve_node(self, snapshot: HierarchySnapshot, ref: UiNodeRef) -> UiNode | None:
        """Resolve a node reference back to the normalized node."""


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _short_class(class_name: str | None) -> str:
    if not class_name:
        return ""
    return class_name.rpartition(".")[2] or class_name


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_attr(element: ET.Element, *names: str) -> str:
    for name in names:
        value = element.get(name)
        if value is not None:
            return value.strip()
    return ""


def _parse_bounds(bounds_str: str) -> UiBounds | None:
    match = _BOUNDS_RE.fullmatch(bounds_str)
    if not match:
        return None
    return UiBounds(
        left=int(match.group(1)),
        top=int(match.group(2)),
        right=int(match.group(3)),
        bottom=int(match.group(4)),
    )


def _normalize_node(element: ET.Element, *, path: tuple[int, ...], backend_path: str) -> UiNode:
    class_name = _read_attr(element, "class", "type") or None
    bounds = _parse_bounds(_read_attr(element, "bounds"))
    visible = not (_read_attr(element, "displayed") == "false" or (bounds is not None and bounds.area == 0))

    children = tuple(
        _normalize_node(
            child,
            path=path + (index,),
            backend_path=f"{backend_path}/{child.tag}[{index}]",
        )
        for index, child in enumerate(list(element), start=1)
    )

    return UiNode(
        ref=UiNodeRef(path=path, backend_path=backend_path),
        tag=_short_class(class_name) or element.tag,
        class_name=class_name,
        text=_read_attr(element, "text"),
        content_desc=_read_attr(element, "content-desc", "description"),
        resource_id=_read_attr(element, "resource-id", "id"),
        package=_read_attr(element, "package", "packageName", "bundleName"),
        bounds=bounds,
        clickable=_truthy(_read_attr(element, "clickable")),
        scrollable=_truthy(_read_attr(element, "scrollable")),
        checkable=_truthy(_read_attr(element, "checkable")),
        checked=_truthy(_read_attr(element, "checked")),
        enabled=not _read_attr(element, "enabled") == "false",
        focused=_truthy(_read_attr(element, "focused")),
        selected=_truthy(_read_attr(element, "selected")),
        visible=visible,
        children=children,
    )


def _has_content(node: UiNode) -> bool:
    return bool(node.text or node.content_desc or node.resource_id)


def _is_interactive(node: UiNode) -> bool:
    return node.clickable or node.scrollable


def _render_node(node: UiNode, lines: list[str], depth: int) -> None:
    if not node.visible:
        return

    if node.tag != "hierarchy" and not _has_content(node) and not _is_interactive(node) and len(node.children) == 1:
        _render_node(node.children[0], lines, depth)
        return

    parts: list[str] = []

    if node.tag and node.tag != "hierarchy":
        parts.append(node.tag)

    if node.text:
        parts.append(f'"{node.text}"')

    if node.content_desc and node.content_desc != node.text:
        parts.append(f'desc="{node.content_desc}"')

    if node.resource_id:
        parts.append(f"#{node.resource_id}")

    if node.bounds is not None:
        parts.append(node.bounds.to_bracket_string())

    flags = []
    if node.clickable:
        flags.append("click")
    if node.scrollable:
        flags.append("scroll")
    if node.checked:
        flags.append("checked")
    if node.focused:
        flags.append("focused")
    if node.selected:
        flags.append("selected")
    if not node.enabled:
        flags.append("disabled")
    if flags:
        parts.append(" ".join(flags))

    child_depth = depth
    if parts:
        lines.append("  " * depth + " ".join(parts))
        child_depth += 1

    for child in node.children:
        _render_node(child, lines, child_depth)


def render_text(snapshot: HierarchySnapshot) -> str:
    """Render a normalized hierarchy snapshot into the compact text tree used by the CLI."""

    lines: list[str] = []
    _render_node(snapshot.root, lines, 0)
    return "\n".join(lines)


def flatten_snapshot(snapshot: HierarchySnapshot, *, include_invisible: bool = False) -> list[UiNode]:
    """Flatten a normalized hierarchy snapshot into document order."""

    flattened: list[UiNode] = []

    def visit(node: UiNode) -> None:
        if include_invisible or node.visible:
            flattened.append(node)
        for child in node.children:
            visit(child)

    visit(snapshot.root)
    return flattened


class BackendHierarchyService:
    """Hierarchy service backed by an automation backend."""

    def __init__(self, backend: AutomationBackend) -> None:
        self._backend = backend

    def capture(self, *, compressed: bool = False, max_depth: int | None = None) -> HierarchySnapshot:
        raw_xml = self._backend.dump_hierarchy_xml(compressed=compressed, max_depth=max_depth)
        root_element = ET.fromstring(raw_xml)
        root_node = _normalize_node(root_element, path=(), backend_path=f"/{root_element.tag}")
        return HierarchySnapshot(
            root=root_node,
            raw_xml=raw_xml,
            platform=self._backend.platform,
            backend_name=self._backend.backend_name,
        )

    def dump(self, *, compressed: bool = False, max_depth: int | None = None, raw: bool = False) -> HierarchyDump:
        snapshot = self.capture(compressed=compressed, max_depth=max_depth)
        output_format = "xml" if raw else "text"
        content = snapshot.raw_xml if raw else render_text(snapshot)
        return HierarchyDump(
            content=content,
            raw_xml=snapshot.raw_xml,
            output_format=output_format,
            platform=snapshot.platform,
            backend_name=snapshot.backend_name,
        )

    def flatten(self, snapshot: HierarchySnapshot, *, include_invisible: bool = False) -> list[UiNode]:
        return flatten_snapshot(snapshot, include_invisible=include_invisible)

    def resolve_node(self, snapshot: HierarchySnapshot, ref: UiNodeRef) -> UiNode | None:
        for node in self.flatten(snapshot, include_invisible=True):
            if node.ref == ref:
                return node
        return None


def hierarchy_to_text(xml_str: str) -> str:
    """Convert raw hierarchy XML to the compact text tree used by the CLI."""

    root_element = ET.fromstring(xml_str)
    snapshot = HierarchySnapshot(
        root=_normalize_node(root_element, path=(), backend_path=f"/{root_element.tag}"),
        raw_xml=xml_str,
        platform="unknown",
        backend_name="unknown",
    )
    return render_text(snapshot)


def create_hierarchy_service(backend: AutomationBackend) -> HierarchyService:
    """Create the hierarchy service for a backend."""

    return BackendHierarchyService(backend)