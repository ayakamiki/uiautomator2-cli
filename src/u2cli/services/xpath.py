"""XPath interaction services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from u2cli.backends.base import AutomationBackend


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

    def resolve(self, expression: str) -> ResolvedLocator:
        parsed = parse_xpath_expression(expression)
        return resolve_xpath_for_platform(parsed, self._backend.platform)

    def click(self, expression: str, *, timeout: float = 3.0) -> None:
        resolved = self.resolve(expression)
        self._backend.locate(resolved.strategy, resolved.value).click(timeout=timeout)

    def get_text(self, expression: str) -> str:
        resolved = self.resolve(expression)
        return self._backend.locate(resolved.strategy, resolved.value).get_text()

    def exists(self, expression: str) -> bool:
        resolved = self.resolve(expression)
        return self._backend.locate(resolved.strategy, resolved.value).exists()

    def set_text(self, expression: str, text: str) -> None:
        resolved = self.resolve(expression)
        self._backend.locate(resolved.strategy, resolved.value).set_text(text)


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