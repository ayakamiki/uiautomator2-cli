"""Service-layer helpers for higher-level cross-platform features."""

from u2cli.services.hierarchy import HierarchyDump, HierarchyService, create_hierarchy_service
from u2cli.services.xpath import (
	ANDROID_XPATH_BOUNDARY,
	HARMONY_LOCATOR_BOUNDARY,
	HARMONY_REQUIRED_LOCATOR_STRATEGIES,
	LocatorCapabilityBoundary,
	ParsedXPath,
	ResolvedLocator,
	XPathService,
	create_xpath_service,
	missing_required_locator_strategies,
	parse_xpath_expression,
	resolve_xpath_for_platform,
)

__all__ = [
	"HierarchyDump",
	"HierarchyService",
	"ANDROID_XPATH_BOUNDARY",
	"HARMONY_LOCATOR_BOUNDARY",
	"HARMONY_REQUIRED_LOCATOR_STRATEGIES",
	"LocatorCapabilityBoundary",
	"ParsedXPath",
	"ResolvedLocator",
	"XPathService",
	"create_hierarchy_service",
	"create_xpath_service",
	"missing_required_locator_strategies",
	"parse_xpath_expression",
	"resolve_xpath_for_platform",
]