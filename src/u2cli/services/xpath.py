"""XPath interaction services."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable, Protocol

from u2cli.backends.base import AutomationBackend
from u2cli.services.hierarchy import HierarchySnapshot, UiNode, create_hierarchy_service, flatten_snapshot


ANDROID_XPATH_STRATEGIES = ("xpath",)
HARMONY_REQUIRED_LOCATOR_STRATEGIES = (
    "xpath",
    "id",
    "text",
    "text_contains",
    "text_regex",
    "text_startswith",
    "text_endswith",
)


@dataclass(frozen=True)
class LocatorCapabilityBoundary:
    """Declared backend capability contract for a family of resolved locators."""

    name: str
    required_strategies: tuple[str, ...]
    note: str


ANDROID_XPATH_BOUNDARY = LocatorCapabilityBoundary(
    name="android_xpath_v1",
    required_strategies=ANDROID_XPATH_STRATEGIES,
    note="Android backends execute service-compiled XPath strings via the xpath locator strategy.",
)


HARMONY_LOCATOR_BOUNDARY = LocatorCapabilityBoundary(
    name="harmony_locator_v1",
    required_strategies=HARMONY_REQUIRED_LOCATOR_STRATEGIES,
    note=(
        "Harmony backends must support the full locator set emitted by XPath shorthand resolution: "
        "xpath, id, text, text_contains, text_regex, text_startswith, text_endswith."
    ),
)


@dataclass(frozen=True)
class ParsedXPath:
    """Semantic representation of a user-provided XPath shorthand expression."""

    kind: str
    value: str
    original: str


@dataclass(frozen=True)
class ResolvedLocator:
    """Backend-facing locator produced by the service layer."""

    strategy: str
    value: str
    original: str
    platform: str
    capability_boundary: LocatorCapabilityBoundary


class XPathService(Protocol):
    """Stable service interface for XPath-driven element interactions."""

    def resolve(self, expression: str) -> ResolvedLocator:
        """Resolve user XPath shorthand to a platform-specific locator."""

    def click(self, expression: str, *, timeout: float = 3.0) -> None:
        """Click an element resolved by XPath."""

    def get_text(self, expression: str) -> str:
        """Read text from an element resolved by XPath."""

    def exists(self, expression: str) -> bool:
        """Check whether an XPath expression resolves to an element."""

    def set_text(self, expression: str, text: str) -> None:
        """Set text on an element resolved by XPath."""


class BackendXPathService:
    """XPath service backed by an automation backend."""

    def __init__(self, backend: AutomationBackend) -> None:
        self._backend = backend
        self._hierarchy_service = create_hierarchy_service(backend)

    def resolve(self, expression: str) -> ResolvedLocator:
        parsed = parse_xpath_expression(expression)
        return resolve_xpath_for_platform(parsed, self._backend.platform)

    def click(self, expression: str, *, timeout: float = 3.0) -> None:
        nodes = self._query_nodes(expression, timeout=timeout)
        if not nodes:
            raise RuntimeError("element not found before timeout")
        self._click_node(nodes[0])

    def get_text(self, expression: str) -> str:
        nodes = self._query_nodes(expression)
        if not nodes:
            raise RuntimeError("element not found")
        return _node_text(nodes[0])

    def exists(self, expression: str) -> bool:
        return bool(self._query_nodes(expression))

    def set_text(self, expression: str, text: str) -> None:
        nodes = self._query_nodes(expression)
        if not nodes:
            raise RuntimeError("element not found")
        self._set_text_on_node(nodes[0], text)

    def _query_nodes(self, expression: str, *, timeout: float = 0.0) -> list[UiNode]:
        parsed = parse_xpath_expression(expression)
        deadline = time.monotonic() + max(0.0, timeout)

        while True:
            snapshot = self._hierarchy_service.capture()
            nodes = query_snapshot(snapshot, parsed)
            if nodes or timeout <= 0:
                return nodes
            if time.monotonic() >= deadline:
                return []
            time.sleep(0.2)

    def _click_node(self, node: UiNode) -> None:
        if node.bounds is not None:
            x, y = node.bounds.center
            self._backend.click(x, y)
            return

        selector = build_selector_from_node(node)
        if selector:
            self._backend.select(selector).click(timeout=0.0)
            return

        raise RuntimeError("matched node is not actionable")

    def _set_text_on_node(self, node: UiNode, text: str) -> None:
        if self._backend.platform == "harmony" and node.bounds is not None:
            if _uses_harmony_manual_replace(node):
                x, y = _harmony_text_end_anchor(node)
                self._backend.click(x, y)
                for _ in range(len(node.text)):
                    self._backend.press("delete")
                self._backend.send_keys(text, clear=False)
                return

            x, y = node.bounds.center
            self._backend.click(x, y)
            self._backend.send_keys(text, clear=True)
            return

        selector = build_selector_from_node(node)
        if selector:
            try:
                self._backend.select(selector).set_text(text, timeout=0.0)
                return
            except Exception:
                pass

        if node.bounds is not None:
            x, y = node.bounds.center
            self._backend.click(x, y)
            self._backend.send_keys(text, clear=True)
            return

        raise RuntimeError("matched node is not actionable")


def parse_xpath_expression(expression: str) -> ParsedXPath:
    """Parse user shorthand into a semantic query understood by the service layer."""

    if expression.lstrip("(").startswith("/"):
        return ParsedXPath(kind="xpath", value=expression, original=expression)
    if expression.startswith("@"):
        return ParsedXPath(kind="resource_id", value=expression[1:], original=expression)
    if expression.startswith("^"):
        return ParsedXPath(kind="text_regex", value=expression, original=expression)
    if expression.startswith("%") and expression.endswith("%"):
        return ParsedXPath(kind="text_contains", value=expression[1:-1], original=expression)
    if expression.startswith("%"):
        return ParsedXPath(kind="text_endswith", value=expression[1:], original=expression)
    if expression.endswith("%"):
        return ParsedXPath(kind="text_startswith", value=expression[:-1], original=expression)
    return ParsedXPath(kind="text_exact", value=expression, original=expression)


def resolve_xpath_for_platform(parsed: ParsedXPath, platform: str) -> ResolvedLocator:
    """Resolve parsed shorthand to a platform-facing locator strategy and value."""

    if platform == "android":
        return ResolvedLocator(
            strategy="xpath",
            value=_compile_android_xpath(parsed),
            original=parsed.original,
            platform=platform,
            capability_boundary=ANDROID_XPATH_BOUNDARY,
        )

    if platform == "harmony":
        return _resolve_harmony_locator(parsed)

    return ResolvedLocator(
        strategy="xpath",
        value=parsed.original,
        original=parsed.original,
        platform=platform,
        capability_boundary=ANDROID_XPATH_BOUNDARY,
    )


def _resolve_harmony_locator(parsed: ParsedXPath) -> ResolvedLocator:
    strategy_map = {
        "xpath": "xpath",
        "resource_id": "id",
        "text_regex": "text_regex",
        "text_contains": "text_contains",
        "text_endswith": "text_endswith",
        "text_startswith": "text_startswith",
        "text_exact": "text",
    }
    return ResolvedLocator(
        strategy=strategy_map[parsed.kind],
        value=parsed.value,
        original=parsed.original,
        platform="harmony",
        capability_boundary=HARMONY_LOCATOR_BOUNDARY,
    )


def missing_required_locator_strategies(boundary: LocatorCapabilityBoundary, supported_strategies: set[str]) -> set[str]:
    """Return the strategies still required for a backend to satisfy the declared boundary."""

    return set(boundary.required_strategies) - set(supported_strategies)


def _compile_android_xpath(parsed: ParsedXPath) -> str:
    if parsed.kind == "xpath":
        xpath = parsed.value
    elif parsed.kind == "resource_id":
        xpath = f"//*[@resource-id={parsed.value!r}]"
    elif parsed.kind == "text_regex":
        regex = repr(parsed.value)
        xpath = (
            f"//*[re:match(@text, {regex}) or re:match(@content-desc, {regex}) "
            f"or re:match(@resource-id, {regex})]"
        )
    elif parsed.kind == "text_contains":
        value = repr(parsed.value)
        xpath = f"//*[contains(@text, {value}) or contains(@content-desc, {value})]"
    elif parsed.kind == "text_endswith":
        value = repr(parsed.value)
        length = len(parsed.value)
        xpath = (
            f"//*[{value} = substring(@text, string-length(@text) - {length} + 1) or "
            f"{value} = substring(@content-desc, string-length(@text) - {length} + 1)]"
        )
    elif parsed.kind == "text_startswith":
        value = repr(parsed.value)
        xpath = f"//*[starts-with(@text, {value}) or starts-with(@content-desc, {value})]"
    else:
        value = repr(parsed.value)
        xpath = f"//*[@text={value} or @content-desc={value} or @resource-id={value}]"
    return xpath.rstrip("/")


def create_xpath_service(backend: AutomationBackend) -> XPathService:
    """Create the XPath service for a backend."""

    return BackendXPathService(backend)


Predicate = Callable[[UiNode], bool]


@dataclass(frozen=True)
class XPathStep:
    """A parsed normalized XPath step."""

    axis: str
    tag: str
    predicates: tuple[object, ...]


class NormalizedXPathEvaluator:
    """Evaluate a small, normalized XPath subset against a hierarchy snapshot."""

    def __init__(self, snapshot: HierarchySnapshot) -> None:
        self._snapshot = snapshot

    def query(self, expression: str) -> list[UiNode]:
        steps = parse_normalized_xpath(expression)
        current = [self._snapshot.root]

        for step in steps:
            if step.axis == "self":
                candidates = current
            elif step.axis == "child":
                candidates = [child for node in current for child in node.children]
            elif step.axis == "descendant":
                candidates = [descendant for node in current for descendant in _descendants_or_self(node)]
            else:
                raise ValueError(f"unsupported normalized XPath axis: {step.axis}")

            matches = [node for node in candidates if _tag_matches(step.tag, node)]
            position_predicates: list[int] = []
            for predicate in step.predicates:
                if isinstance(predicate, int):
                    position_predicates.append(predicate)
                    continue
                matches = [node for node in matches if predicate(node)]

            for position in position_predicates:
                index = position - 1
                matches = [matches[index]] if 0 <= index < len(matches) else []

            current = matches

        return [node for node in current if node.tag != "hierarchy"]


def build_selector_from_node(node: UiNode) -> dict[str, object]:
    """Build a backend selector from a normalized node when possible."""

    selector: dict[str, object] = {}
    if node.package:
        selector["packageName"] = node.package
    if node.resource_id:
        selector["resourceId"] = node.resource_id
    if node.class_name:
        selector["className"] = node.class_name
    if node.text:
        selector["text"] = node.text
    if node.content_desc:
        selector["description"] = node.content_desc
    return selector


def query_snapshot(snapshot: HierarchySnapshot, parsed: ParsedXPath) -> list[UiNode]:
    """Query a normalized hierarchy snapshot using either shorthand or full XPath syntax."""

    if parsed.kind == "xpath":
        return NormalizedXPathEvaluator(snapshot).query(parsed.value)

    nodes = _flatten_queryable_nodes(snapshot)
    if parsed.kind == "resource_id":
        return [node for node in nodes if node.resource_id == parsed.value]
    if parsed.kind == "text_regex":
        regex = re.compile(parsed.value)
        return [node for node in nodes if any(regex.search(value) for value in _node_match_values(node))]
    if parsed.kind == "text_contains":
        return [node for node in nodes if any(parsed.value in value for value in _node_match_values(node, include_resource_id=False))]
    if parsed.kind == "text_endswith":
        return [node for node in nodes if any(value.endswith(parsed.value) for value in _node_match_values(node, include_resource_id=False))]
    if parsed.kind == "text_startswith":
        return [node for node in nodes if any(value.startswith(parsed.value) for value in _node_match_values(node, include_resource_id=False))]
    return [node for node in nodes if any(value == parsed.value for value in _node_match_values(node))]


def parse_normalized_xpath(expression: str) -> list[XPathStep]:
    """Parse a restricted XPath subset into normalized steps."""

    expression = expression.strip()
    if not expression.startswith("/"):
        raise ValueError(f"unsupported normalized XPath expression: {expression}")

    steps: list[XPathStep] = []
    position = 0
    next_axis = "descendant" if expression.startswith("//") else "self"
    position = 2 if expression.startswith("//") else 1

    while position <= len(expression):
        start = position
        bracket_depth = 0
        quote_char: str | None = None

        while position < len(expression):
            char = expression[position]
            if quote_char is not None:
                if char == quote_char:
                    quote_char = None
            elif char in {"'", '"'}:
                quote_char = char
            elif char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
            elif bracket_depth == 0 and expression.startswith("//", position):
                break
            elif bracket_depth == 0 and char == "/":
                break
            position += 1

        step_source = expression[start:position].strip()
        if step_source:
            tag, predicates = _parse_step(step_source)
            steps.append(XPathStep(axis=next_axis, tag=tag, predicates=predicates))

        if position >= len(expression):
            break
        next_axis = "descendant" if expression.startswith("//", position) else "child"
        position += 2 if next_axis == "descendant" else 1

    return steps


def _parse_step(step_source: str) -> tuple[str, tuple[object, ...]]:
    tag_chars: list[str] = []
    predicates: list[object] = []
    position = 0

    while position < len(step_source) and step_source[position] != "[":
        tag_chars.append(step_source[position])
        position += 1

    tag = "".join(tag_chars).strip() or "*"

    while position < len(step_source):
        if step_source[position] != "[":
            position += 1
            continue
        position += 1
        start = position
        depth = 1
        quote_char: str | None = None
        while position < len(step_source) and depth > 0:
            char = step_source[position]
            if quote_char is not None:
                if char == quote_char:
                    quote_char = None
            elif char in {"'", '"'}:
                quote_char = char
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    break
            position += 1
        predicate_source = step_source[start:position].strip()
        predicates.append(_compile_predicate(predicate_source))
        position += 1

    return tag, tuple(predicates)


def _compile_predicate(source: str) -> object:
    source = source.strip()
    if source.isdigit():
        return int(source)

    or_parts = _split_top_level(source, " or ")
    if len(or_parts) > 1:
        compiled = [_compile_predicate(part) for part in or_parts]
        return lambda node: any(_apply_predicate(part, node) for part in compiled)

    and_parts = _split_top_level(source, " and ")
    if len(and_parts) > 1:
        compiled = [_compile_predicate(part) for part in and_parts]
        return lambda node: all(_apply_predicate(part, node) for part in compiled)

    attr_eq = re.fullmatch(r"@([\w:-]+)\s*=\s*(['\"])(.*?)\2", source)
    if attr_eq:
        attr_name = attr_eq.group(1)
        expected = attr_eq.group(3)
        return lambda node: any(value == expected for value in _node_attr_values(node, attr_name))

    contains = re.fullmatch(r"contains\(@([\w:-]+),\s*(['\"])(.*?)\2\)", source)
    if contains:
        attr_name = contains.group(1)
        expected = contains.group(3)
        return lambda node: any(expected in value for value in _node_attr_values(node, attr_name))

    starts_with = re.fullmatch(r"starts-with\(@([\w:-]+),\s*(['\"])(.*?)\2\)", source)
    if starts_with:
        attr_name = starts_with.group(1)
        expected = starts_with.group(3)
        return lambda node: any(value.startswith(expected) for value in _node_attr_values(node, attr_name))

    ends_with = re.fullmatch(r"ends-with\(@([\w:-]+),\s*(['\"])(.*?)\2\)", source)
    if ends_with:
        attr_name = ends_with.group(1)
        expected = ends_with.group(3)
        return lambda node: any(value.endswith(expected) for value in _node_attr_values(node, attr_name))

    regex_match = re.fullmatch(r"re:match\(@([\w:-]+),\s*(['\"])(.*?)\2\)", source)
    if regex_match:
        attr_name = regex_match.group(1)
        expected = re.compile(regex_match.group(3))
        return lambda node: any(expected.search(value) for value in _node_attr_values(node, attr_name))

    raise ValueError(f"unsupported normalized XPath predicate: {source}")


def _apply_predicate(predicate: object, node: UiNode) -> bool:
    if isinstance(predicate, int):
        raise ValueError("positional predicates must be applied at the node-set level")
    return bool(predicate(node))


def _split_top_level(source: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote_char: str | None = None
    index = 0

    while index < len(source):
        char = source[index]
        if quote_char is not None:
            if char == quote_char:
                quote_char = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote_char = char
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and source.startswith(delimiter, index):
            parts.append(source[start:index].strip())
            index += len(delimiter)
            start = index
            continue
        index += 1

    if start == 0:
        return [source]

    parts.append(source[start:].strip())
    return parts


def _tag_matches(tag: str, node: UiNode) -> bool:
    if tag == "*":
        return True
    candidates = {node.tag}
    if node.class_name:
        candidates.add(node.class_name)
        candidates.add(node.class_name.rpartition(".")[2] or node.class_name)
    return tag in candidates


def _descendants_or_self(node: UiNode):
    yield node
    for child in node.children:
        yield from _descendants_or_self(child)


def _flatten_queryable_nodes(snapshot: HierarchySnapshot) -> list[UiNode]:
    nodes = flatten_snapshot(snapshot)
    return [node for node in nodes if node.tag != "hierarchy"]


def _node_attr_values(node: UiNode, attr_name: str) -> list[str]:
    attr_map = {
        "text": [node.text],
        "content-desc": [node.content_desc],
        "description": [node.content_desc],
        "resource-id": [node.resource_id],
        "id": [node.resource_id],
        "package": [node.package],
        "packageName": [node.package],
        "bundleName": [node.package],
        "class": [node.class_name or node.tag],
        "type": [node.class_name or node.tag],
        "clickable": [str(node.clickable).lower()],
        "scrollable": [str(node.scrollable).lower()],
        "checked": [str(node.checked).lower()],
        "focused": [str(node.focused).lower()],
        "selected": [str(node.selected).lower()],
        "enabled": [str(node.enabled).lower()],
    }
    return [value for value in attr_map.get(attr_name, []) if value]


def _node_match_values(node: UiNode, *, include_resource_id: bool = True) -> tuple[str, ...]:
    values = [node.text, node.content_desc]
    if include_resource_id:
        values.append(node.resource_id)
    return tuple(value for value in values if value)


def _node_text(node: UiNode) -> str:
    return node.text or node.content_desc or node.resource_id


def _harmony_node_candidates(node: UiNode) -> set[str]:
    candidates = {node.tag}
    if node.class_name:
        candidates.add(node.class_name)
        candidates.add(node.class_name.rpartition(".")[2] or node.class_name)
    return candidates


def _uses_harmony_manual_replace(node: UiNode) -> bool:
    return bool(_harmony_node_candidates(node) & {"RichEditor", "TextInput"})


def _harmony_text_end_anchor(node: UiNode) -> tuple[int, int]:
    if node.bounds is None:
        raise RuntimeError("matched Harmony text node is missing bounds")

    x = max(node.bounds.left + 1, node.bounds.right - 10)
    vertical_offset = max(1, min(140, node.bounds.height // 6))
    y = min(node.bounds.bottom - 1, node.bounds.top + vertical_offset)
    return x, y