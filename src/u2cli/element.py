"""Element selector and action commands for u2cli.

Commands in this module resolve a shared cross-platform selector surface and
then perform actions on the matched element.
"""

from __future__ import annotations

import click

from u2cli.device import build_selector_repr, connect_backend, output_result
from u2cli.services import create_hierarchy_service, create_xpath_service
from u2cli.services.xpath import find_selector_node, node_is_drop_surface

# ---------------------------------------------------------------------------
# Selector option helpers
# ---------------------------------------------------------------------------

SELECTOR_OPTION_SPECS = [
    {"name": "text", "option": "--text", "help": "Exact text match"},
    {"name": "text_contains", "option": "--text-contains", "help": "Text contains substring"},
    {"name": "text_matches", "option": "--text-matches", "help": "Text matches regex"},
    {"name": "text_starts_with", "option": "--text-starts-with", "help": "Text starts with prefix"},
    {"name": "resource_id", "option": "--resource-id", "help": "Resource/element ID (e.g. com.pkg:id/btn)"},
    {"name": "class_name", "option": "--class-name", "help": "UI class name"},
    {"name": "description", "option": "--description", "help": "Accessibility description (exact)"},
    {"name": "description_contains", "option": "--description-contains", "help": "Accessibility description contains"},
    {"name": "description_matches", "option": "--description-matches", "help": "Accessibility description matches regex"},
    {"name": "description_starts_with", "option": "--description-starts-with", "help": "Accessibility description starts with prefix"},
    {
        "name": "package",
        "option": "--package",
        "help": "Package/bundle filter (Android package name; Harmony hierarchy bundle filter)",
    },
    {"name": "index", "option": "--index", "type": int, "help": "Sibling index"},
    {"name": "instance", "option": "--instance", "type": int, "help": "Global instance index (0-based)"},
    {"name": "checkable", "option": "--checkable", "is_flag": True, "default": None, "help": "Element is checkable"},
    {"name": "checked", "option": "--checked", "is_flag": True, "default": None, "help": "Element is checked"},
    {"name": "clickable", "option": "--clickable", "is_flag": True, "default": None, "help": "Element is clickable"},
    {"name": "scrollable", "option": "--scrollable", "is_flag": True, "default": None, "help": "Element is scrollable"},
    {"name": "enabled", "option": "--enabled", "is_flag": True, "default": None, "help": "Element is enabled"},
    {"name": "focused", "option": "--focused", "is_flag": True, "default": None, "help": "Element is focused"},
    {"name": "selected", "option": "--selected", "is_flag": True, "default": None, "help": "Element is selected"},
]

SELECTOR_OPTION_NAMES = tuple(spec["name"] for spec in SELECTOR_OPTION_SPECS)


def _make_selector_options(*, prefix: str = "", label_prefix: str = ""):
    options = []
    param_prefix = prefix.rstrip("-").replace("-", "_")
    for spec in SELECTOR_OPTION_SPECS:
        option_name = spec["option"] if not prefix else f"--{prefix}{spec['option'][2:]}"
        decorator_kwargs = {
            "default": spec.get("default", None),
            "help": f"{label_prefix}{spec['help']}" if label_prefix else spec["help"],
        }
        if spec.get("is_flag"):
            decorator_kwargs["is_flag"] = True
        if "type" in spec:
            decorator_kwargs["type"] = spec["type"]
        param_decls = [option_name]
        if prefix:
            param_decls.append(f"{param_prefix}_{spec['name']}")
        options.append(click.option(*param_decls, **decorator_kwargs))
    return options


SELECTOR_OPTIONS = _make_selector_options()
TARGET_SELECTOR_OPTIONS = _make_selector_options(prefix="target-", label_prefix="Target element: ")


def add_selector_options(func):
    """Decorator: attach all selector options to a Click command."""
    for option in reversed(SELECTOR_OPTIONS):
        func = option(func)
    return func


def add_target_selector_options(func):
    """Decorator: attach target-selector options to a Click command."""
    for option in reversed(TARGET_SELECTOR_OPTIONS):
        func = option(func)
    return func


def build_selector_kwargs(**kwargs) -> dict:
    """Build a clean selector kwargs dict from CLI options (skip None/False)."""
    mapping = {
        "text": "text",
        "text_contains": "textContains",
        "text_matches": "textMatches",
        "text_starts_with": "textStartsWith",
        "resource_id": "resourceId",
        "class_name": "className",
        "description": "description",
        "description_contains": "descriptionContains",
        "description_matches": "descriptionMatches",
        "description_starts_with": "descriptionStartsWith",
        "package": "packageName",
        "index": "index",
        "instance": "instance",
        "checkable": "checkable",
        "checked": "checked",
        "clickable": "clickable",
        "scrollable": "scrollable",
        "enabled": "enabled",
        "focused": "focused",
        "selected": "selected",
    }
    result = {}
    for cli_name, u2_name in mapping.items():
        val = kwargs.get(cli_name)
        if val is not None and val is not False:
            result[u2_name] = val
    return result


def _require_selector(kwargs: dict) -> tuple[dict, str]:
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")
    return sel, build_selector_repr(sel)


def _split_drag_selector_kwargs(kwargs: dict) -> tuple[dict, dict]:
    source_kwargs = {key: kwargs.get(key) for key in SELECTOR_OPTION_NAMES}
    target_kwargs = {key: kwargs.get(f"target_{key}") for key in SELECTOR_OPTION_NAMES}
    return source_kwargs, target_kwargs


def _resolve_node_by_path(root, path):
    node = root
    current_path = ()
    for step in path:
        next_path = current_path + (step,)
        node = next((child for child in node.children if child.ref.path == next_path), None)
        if node is None:
            return None
        current_path = next_path
    return node


def _choose_harmony_drag_anchor(snapshot, node):
    if node is None or node.bounds is None:
        return node
    if node.clickable:
        return node

    center_x, center_y = node.bounds.center
    path = node.ref.path
    while path:
        path = path[:-1]
        parent = _resolve_node_by_path(snapshot.root, path)
        if parent is None or parent.bounds is None or not parent.clickable:
            continue

        if (
            parent.bounds.left <= center_x <= parent.bounds.right
            and parent.bounds.top <= center_y <= parent.bounds.bottom
        ):
            return parent

    return node


def _drag_via_drop_surface_if_needed(backend, source_sel: dict, target_sel: dict, *, duration: float) -> bool:
    snapshot = create_hierarchy_service(backend).capture()
    source_node = find_selector_node(snapshot, source_sel)
    target_node = find_selector_node(snapshot, target_sel)

    if source_node is None or target_node is None:
        return False

    if getattr(backend, "platform", None) == "harmony":
        source_node = _choose_harmony_drag_anchor(snapshot, source_node)
        target_node = _choose_harmony_drag_anchor(snapshot, target_node)

    if source_node.bounds is None or target_node.bounds is None:
        return False

    # Harmony text selectors commonly resolve to label nodes where native
    # object-to-object drag_to can fail; coordinate dragging is more robust.
    if getattr(backend, "platform", None) != "harmony" and not node_is_drop_surface(target_node):
        return False

    start_x, start_y = source_node.bounds.center
    end_x, end_y = target_node.bounds.center
    backend.drag_and_drop(start_x, start_y, end_x, end_y, duration=duration)
    return True


def _validate_unsigned_percent(percent: float) -> None:
    if percent <= 0 or percent > 100:
        raise click.UsageError("--percent must be greater than 0 and less than or equal to 100.")


# ---------------------------------------------------------------------------
# Element commands
# ---------------------------------------------------------------------------


@click.command("click")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_click(timeout, **kwargs):
    """Click on a UI element matching the given selector."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).click(timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).click(timeout=timeout)
    output_result(None, u2_code)


@click.command("long-click")
@click.option("--duration", default=0.5, type=float, help="Long press duration in seconds")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_long_click(duration, timeout, **kwargs):
    """Long-click on a UI element."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).long_click(duration={duration}, timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).long_click(duration=duration, timeout=timeout)
    output_result(None, u2_code)


@click.command("get-text")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_get_text(timeout, **kwargs):
    """Get the text of a UI element."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).get_text(timeout={timeout})"

    backend = connect_backend()
    text = backend.select(sel).get_text(timeout=timeout)
    output_result(text, u2_code)


@click.command("set-text")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@click.argument("text")
@add_selector_options
def cmd_set_text(timeout, text, **kwargs):
    """Set text on a UI element (clears existing text first)."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).set_text({text!r}, timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).set_text(text, timeout=timeout)
    output_result(None, u2_code)


@click.command("clear-text")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_clear_text(timeout, **kwargs):
    """Clear text from a UI element."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).clear_text(timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).clear_text(timeout=timeout)
    output_result(None, u2_code)


@click.command("exists")
@click.option("--timeout", default=0.0, type=float, help="Wait up to this many seconds")
@add_selector_options
def cmd_exists(timeout, **kwargs):
    """Check whether a UI element exists."""
    sel, sel_repr = _require_selector(kwargs)
    if timeout:
        u2_code = f"d({sel_repr}).exists(timeout={timeout})"
    else:
        u2_code = f"d({sel_repr}).exists"

    backend = connect_backend()
    exists = backend.select(sel).exists(timeout=timeout)
    output_result(bool(exists), u2_code)


@click.command("wait")
@click.option("--timeout", default=3.0, type=float, help="Timeout in seconds")
@click.option(
    "--gone",
    is_flag=True,
    default=False,
    help="Wait for element to disappear instead of appear",
)
@add_selector_options
def cmd_wait(timeout, gone, **kwargs):
    """Wait for a UI element to appear (or disappear with --gone)."""
    sel, sel_repr = _require_selector(kwargs)
    if gone:
        u2_code = f"d({sel_repr}).wait_gone(timeout={timeout})"
    else:
        u2_code = f"d({sel_repr}).wait(timeout={timeout})"

    backend = connect_backend()
    result = backend.select(sel).wait(timeout=timeout, gone=gone)
    output_result(result, u2_code)


@click.command("info")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_element_info(timeout, **kwargs):
    """Get detailed info about a UI element."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).info"

    backend = connect_backend()
    info = backend.select(sel).info()
    output_result(info, u2_code)


@click.command("swipe-element")
@click.option(
    "--direction",
    type=click.Choice(["left", "right", "up", "down"]),
    required=True,
    help="Swipe direction",
)
@click.option("--steps", default=10, type=int, help="Number of swipe steps")
@add_selector_options
def cmd_swipe_element(direction, steps, **kwargs):
    """Swipe on a UI element in the given direction."""
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).swipe({direction!r}, steps={steps})"

    backend = connect_backend()
    backend.select(sel).swipe(direction, steps=steps)
    output_result(None, u2_code)


@click.command("scroll")
@click.option(
    "--direction",
    type=click.Choice(["vert", "horiz"]),
    default="vert",
    help="Scroll axis",
)
@click.option(
    "--action",
    type=click.Choice(["forward", "backward", "toEnd", "toBeginning"]),
    default="forward",
    help="Scroll action",
)
@click.option("--max-swipes", default=None, type=int, help="Max swipes (for toEnd/toBeginning)")
@click.option(
    "--to-text",
    default=None,
    help="Scroll until child with this text is visible",
)
@add_selector_options
def cmd_scroll(direction, action, max_swipes, to_text, **kwargs):
    """Scroll a scrollable UI element."""
    sel, sel_repr = _require_selector(kwargs)
    backend = connect_backend()

    if to_text:
        u2_code = f"d({sel_repr}).scroll.{direction}.to(text={to_text!r})"
        backend.select(sel).scroll(direction=direction, action=action, to_text=to_text)
    elif max_swipes is not None:
        u2_code = f"d({sel_repr}).scroll.{direction}.{action}(max_swipes={max_swipes})"
        backend.select(sel).scroll(direction=direction, action=action, max_swipes=max_swipes)
    else:
        u2_code = f"d({sel_repr}).scroll.{direction}.{action}()"
        backend.select(sel).scroll(direction=direction, action=action)

    output_result(None, u2_code)


@click.command("pinch-in")
@click.option("--percent", default=100.0, type=float, help="Pinch extent percentage (1-100)")
@add_selector_options
def cmd_pinch_in(percent, **kwargs):
    """Pinch in on a UI element matching the given selector."""
    _validate_unsigned_percent(percent)
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).pinch_in(percent={percent})"

    backend = connect_backend()
    backend.select(sel).pinch_in(percent=percent)
    output_result(None, u2_code)


@click.command("pinch-out")
@click.option("--percent", default=100.0, type=float, help="Pinch extent percentage (1-100)")
@add_selector_options
def cmd_pinch_out(percent, **kwargs):
    """Pinch out on a UI element matching the given selector."""
    _validate_unsigned_percent(percent)
    sel, sel_repr = _require_selector(kwargs)
    u2_code = f"d({sel_repr}).pinch_out(percent={percent})"

    backend = connect_backend()
    backend.select(sel).pinch_out(percent=percent)
    output_result(None, u2_code)


@click.command("drag-and-drop-element")
@click.option("--duration", default=0.5, type=float, help="Drag duration in seconds")
@add_target_selector_options
@add_selector_options
def cmd_drag_and_drop_element(duration, **kwargs):
    """Drag one UI element onto another UI element."""
    source_kwargs, target_kwargs = _split_drag_selector_kwargs(kwargs)
    source_sel, source_repr = _require_selector(source_kwargs)
    target_sel, target_repr = _require_selector(target_kwargs)
    u2_code = f"d({source_repr}).drag_to(d({target_repr}), duration={duration})"

    backend = connect_backend()
    if _drag_via_drop_surface_if_needed(backend, source_sel, target_sel, duration=duration):
        output_result(None, u2_code)
        return

    source = backend.select(source_sel)
    target = backend.select(target_sel)
    source.drag_to(target, duration=duration)
    output_result(None, u2_code)


@click.command("xpath-click")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@click.argument("xpath", metavar="LOCATOR")
def cmd_xpath_click(timeout, xpath):
    """Click on an element resolved from a locator expression.

    Supports full XPath plus shorthand forms such as @id, ^regex,
    %contains%, prefix%, %suffix, and plain text.
    """
    u2_code = f"d.xpath({xpath!r}).click(timeout={timeout})"
    backend = connect_backend()
    create_xpath_service(backend).click(xpath, timeout=timeout)
    output_result(None, u2_code)


@click.command("xpath-get-text")
@click.argument("xpath", metavar="LOCATOR")
def cmd_xpath_get_text(xpath):
    """Get text from an element resolved from a locator expression."""
    u2_code = f"d.xpath({xpath!r}).get_text()"
    backend = connect_backend()
    text = create_xpath_service(backend).get_text(xpath)
    output_result(text, u2_code)


@click.command("xpath-exists")
@click.argument("xpath", metavar="LOCATOR")
def cmd_xpath_exists(xpath):
    """Check whether a locator expression resolves to an element."""
    u2_code = f"d.xpath({xpath!r}).exists"
    backend = connect_backend()
    exists = create_xpath_service(backend).exists(xpath)
    output_result(bool(exists), u2_code)


@click.command("xpath-set-text")
@click.argument("xpath", metavar="LOCATOR")
@click.argument("text")
def cmd_xpath_set_text(xpath, text):
    """Set text on an element resolved from a locator expression."""
    u2_code = f"d.xpath({xpath!r}).set_text({text!r})"
    backend = connect_backend()
    create_xpath_service(backend).set_text(xpath, text)
    output_result(None, u2_code)


@click.command("drag-and-drop-xpath")
@click.option("--duration", default=0.5, type=float, help="Drag duration in seconds")
@click.argument("source_xpath", metavar="SOURCE_LOCATOR")
@click.argument("target_xpath", metavar="TARGET_LOCATOR")
def cmd_drag_and_drop_xpath(duration, source_xpath, target_xpath):
    """Drag one XPath-resolved element onto another XPath-resolved element."""
    u2_code = f"d.xpath({source_xpath!r}).drag_to(d.xpath({target_xpath!r}), duration={duration})"
    backend = connect_backend()
    create_xpath_service(backend).drag_and_drop(source_xpath, target_xpath, duration=duration)
    output_result(None, u2_code)
