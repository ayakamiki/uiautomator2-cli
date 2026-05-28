"""Element selector and action commands for u2cli.

Commands in this module resolve a shared cross-platform selector surface and
then perform actions on the matched element.
"""

from __future__ import annotations

import click

from u2cli.device import build_selector_repr, connect_backend, output_result
from u2cli.services import create_xpath_service

# ---------------------------------------------------------------------------
# Selector option helpers
# ---------------------------------------------------------------------------

SELECTOR_OPTIONS = [
    click.option("--text", default=None, help="Exact text match"),
    click.option("--text-contains", default=None, help="Text contains substring"),
    click.option("--text-matches", default=None, help="Text matches regex"),
    click.option("--text-starts-with", default=None, help="Text starts with prefix"),
    click.option("--resource-id", default=None, help="Resource/element ID (e.g. com.pkg:id/btn)"),
    click.option("--class-name", default=None, help="UI class name"),
    click.option("--description", default=None, help="Accessibility description (exact)"),
    click.option("--description-contains", default=None, help="Accessibility description contains"),
    click.option("--description-matches", default=None, help="Accessibility description matches regex"),
    click.option("--description-starts-with", default=None, help="Accessibility description starts with prefix"),
    click.option(
        "--package",
        default=None,
        help="Package/bundle filter (Android package name; Harmony hierarchy bundle filter)",
    ),
    click.option("--index", default=None, type=int, help="Sibling index"),
    click.option("--instance", default=None, type=int, help="Global instance index (0-based)"),
    click.option("--checkable", is_flag=True, default=None, help="Element is checkable"),
    click.option("--checked", is_flag=True, default=None, help="Element is checked"),
    click.option("--clickable", is_flag=True, default=None, help="Element is clickable"),
    click.option("--scrollable", is_flag=True, default=None, help="Element is scrollable"),
    click.option("--enabled", is_flag=True, default=None, help="Element is enabled"),
    click.option("--focused", is_flag=True, default=None, help="Element is focused"),
    click.option("--selected", is_flag=True, default=None, help="Element is selected"),
]


def add_selector_options(func):
    """Decorator: attach all selector options to a Click command."""
    for option in reversed(SELECTOR_OPTIONS):
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


# ---------------------------------------------------------------------------
# Element commands
# ---------------------------------------------------------------------------


@click.command("click")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_click(timeout, **kwargs):
    """Click on a UI element matching the given selector."""
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
    u2_code = f"d({sel_repr}).long_click(duration={duration}, timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).long_click(duration=duration, timeout=timeout)
    output_result(None, u2_code)


@click.command("get-text")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_get_text(timeout, **kwargs):
    """Get the text of a UI element."""
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
    u2_code = f"d({sel_repr}).set_text({text!r}, timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).set_text(text, timeout=timeout)
    output_result(None, u2_code)


@click.command("clear-text")
@click.option("--timeout", default=3.0, type=float, help="Wait timeout in seconds")
@add_selector_options
def cmd_clear_text(timeout, **kwargs):
    """Clear text from a UI element."""
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
    u2_code = f"d({sel_repr}).clear_text(timeout={timeout})"

    backend = connect_backend()
    backend.select(sel).clear_text(timeout=timeout)
    output_result(None, u2_code)


@click.command("exists")
@click.option("--timeout", default=0.0, type=float, help="Wait up to this many seconds")
@add_selector_options
def cmd_exists(timeout, **kwargs):
    """Check whether a UI element exists."""
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
    sel = build_selector_kwargs(**kwargs)
    if not sel:
        raise click.UsageError("At least one selector option is required.")

    sel_repr = build_selector_repr(sel)
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
