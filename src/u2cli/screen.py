"""Device-level commands for u2cli.

Commands that operate on the device as a whole (not on individual elements):
screenshot, dump-hierarchy, press, swipe, info, shell, send-keys, etc.
"""

from __future__ import annotations

import json
import os

import click

from u2cli.backends.factory import resolve_platform
from u2cli.backends.harmony_hm import run_harmony_media_control_if_available
from u2cli.device import connect_backend, output_result
from u2cli.services import create_hierarchy_service


def _harmony_partial_extra(note: str, **extra):
    payload = {
        "partial": True,
        "support_level": "partial",
        "note": note,
    }
    payload.update(extra)
    return payload


def _validate_zoom_percent(percent: float) -> None:
    if percent == 0 or abs(percent) > 100:
        raise click.UsageError("--percent must be non-zero and its absolute value must be less than or equal to 100.")

# ---------------------------------------------------------------------------
# Device info & screen
# ---------------------------------------------------------------------------


@click.command("device-info")
def cmd_device_info():
    """Show device information (platform, model, screen size, etc. when available)."""
    u2_code = "d.device_info"
    backend = connect_backend()
    info = backend.device_info()
    output_result(info, u2_code)


@click.command("ui-info")
def cmd_ui_info():
    """Show UI runtime info (screen size, orientation, current app, platform)."""
    u2_code = "d.info"
    backend = connect_backend()
    info = backend.ui_info()
    output_result(info, u2_code)


@click.command("screenshot")
@click.argument("filename", default="screenshot.png")
def cmd_screenshot(filename):
    """Take a screenshot and save to FILENAME (default: screenshot.png)."""
    u2_code = f"d.screenshot({filename!r})"
    backend = connect_backend()
    abs_path = os.path.abspath(filename)
    img = backend.screenshot()
    width, height = img.size
    img.save(abs_path)
    output_result(None, u2_code, extra={"saved_to": abs_path, "resolution": f"{width}x{height}"})


@click.command("dump-hierarchy")
@click.option("--compressed", is_flag=True, default=False, help="Use compressed hierarchy")
@click.option("--max-depth", default=None, type=int, help="Maximum hierarchy depth")
@click.option("--output", "-o", default=None, help="Save output to file instead of stdout")
@click.option("--raw", is_flag=True, default=False, help="Output raw XML without simplification")
def cmd_dump_hierarchy(compressed, max_depth, output, raw):
    """Dump the UI hierarchy as a compact indented text tree.

    Invisible nodes, pure-container nodes, and noise attributes are removed.
    Pass --raw to get the original backend XML output.
    """
    kwargs_parts = []
    if compressed:
        kwargs_parts.append("compressed=True")
    if max_depth is not None:
        kwargs_parts.append(f"max_depth={max_depth}")
    u2_code = f"d.dump_hierarchy({', '.join(kwargs_parts)})"

    backend = connect_backend()
    hierarchy = create_hierarchy_service(backend).dump(compressed=compressed, max_depth=max_depth, raw=raw)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(hierarchy.content)
        output_result(None, u2_code, extra={"saved_to": os.path.abspath(output)})
    else:
        output_result(hierarchy.content, u2_code)


@click.command("window-size")
def cmd_window_size():
    """Get the screen window size (width, height)."""
    u2_code = "d.window_size()"
    backend = connect_backend()
    w, h = backend.window_size()
    output_result({"width": w, "height": h}, u2_code)


# ---------------------------------------------------------------------------
# Screen on/off & orientation
# ---------------------------------------------------------------------------


@click.command("screen-on")
def cmd_screen_on():
    """Turn the screen on (wake device)."""
    u2_code = "d.screen_on()"
    backend = connect_backend()
    backend.screen_on()
    output_result(None, u2_code)


@click.command("screen-off")
def cmd_screen_off():
    """Turn the screen off (sleep device)."""
    u2_code = "d.screen_off()"
    backend = connect_backend()
    backend.screen_off()
    output_result(None, u2_code)


@click.command("orientation")
@click.option(
    "--set",
    "set_orientation",
    default=None,
    type=click.Choice(["natural", "left", "right", "upsidedown"]),
    help="Set screen orientation",
)
def cmd_orientation(set_orientation):
    """Get or set screen orientation."""
    backend = connect_backend()
    if set_orientation:
        u2_code = f"d.orientation = {set_orientation!r}"
        backend.set_orientation(set_orientation)
        output_result(None, u2_code)
    else:
        u2_code = "d.orientation"
        orientation = backend.get_orientation()
        output_result(orientation, u2_code)


# ---------------------------------------------------------------------------
# Input: press key, swipe, click, send-keys
# ---------------------------------------------------------------------------


@click.command("press")
@click.argument("key", metavar="KEY")
def cmd_press(key):
    """Press a hardware/soft key by name or keycode integer.

    Common named keys: home, back, menu, enter, delete, recent,
    volume_up, volume_down, power.

    Harmony real-device validated aliases: home, back, recent, menu,
    enter, delete, volume_up, volume_down, power.
    On the current Harmony test device, enter/delete were also verified end to
    end inside a real note-editor input field. Other named keys are
    backend-dependent; use an integer keycode when you need an unmapped key.
    """
    key_val: int | str
    try:
        key_val = int(key)
        u2_code = f"d.press({key_val})"
    except ValueError:
        key_val = key
        u2_code = f"d.press({key_val!r})"

    backend = connect_backend()
    backend.press(key_val)
    output_result(None, u2_code)


@click.command("swipe")
@click.option("--duration", default=0.5, type=float, help="Swipe duration in seconds")
@click.option("--steps", default=None, type=int, help="Number of steps (overrides duration)")
@click.argument("fx", type=float)
@click.argument("fy", type=float)
@click.argument("tx", type=float)
@click.argument("ty", type=float)
def cmd_swipe(duration, steps, fx, fy, tx, ty):
    """Swipe from (FX, FY) to (TX, TY). Coords can be 0-1 (relative) or pixels."""
    if steps is not None:
        u2_code = f"d.swipe({fx}, {fy}, {tx}, {ty}, steps={steps})"
    else:
        u2_code = f"d.swipe({fx}, {fy}, {tx}, {ty}, duration={duration})"

    backend = connect_backend()
    if steps is not None:
        backend.swipe(fx, fy, tx, ty, steps=steps)
    else:
        backend.swipe(fx, fy, tx, ty, duration=duration)
    output_result(None, u2_code)


@click.command("swipe-ext")
@click.option("--scale", default=0.8, type=float, help="Swipe distance as fraction of screen")
@click.argument(
    "direction",
    type=click.Choice(["left", "right", "up", "down"]),
)
def cmd_swipe_ext(scale, direction):
    """High-level directional swipe across the screen."""
    u2_code = f"d.swipe_ext({direction!r}, scale={scale})"
    backend = connect_backend()
    backend.swipe_ext(direction, scale=scale)
    output_result(None, u2_code)


@click.command("click-coord")
@click.argument("x", type=float)
@click.argument("y", type=float)
def cmd_click_coord(x, y):
    """Click at absolute or relative (0-1) coordinates."""
    u2_code = f"d.click({x}, {y})"
    backend = connect_backend()
    backend.click(x, y)
    output_result(None, u2_code)


@click.command("double-click")
@click.option("--duration", default=0.1, type=float, help="Delay between taps")
@click.argument("x", type=float)
@click.argument("y", type=float)
def cmd_double_click(duration, x, y):
    """Double-click at coordinates."""
    u2_code = f"d.double_click({x}, {y}, duration={duration})"
    backend = connect_backend()
    backend.double_click(x, y, duration=duration)
    output_result(None, u2_code)


@click.command("long-click-coord")
@click.option("--duration", default=0.5, type=float, help="Long press duration in seconds")
@click.argument("x", type=float)
@click.argument("y", type=float)
def cmd_long_click_coord(duration, x, y):
    """Long-click at coordinates."""
    u2_code = f"d.long_click({x}, {y}, duration={duration})"
    backend = connect_backend()
    backend.long_click(x, y, duration=duration)
    output_result(None, u2_code)


@click.command("drag-and-drop")
@click.option("--duration", default=0.5, type=float, help="Drag duration in seconds")
@click.argument("fx", type=float)
@click.argument("fy", type=float)
@click.argument("tx", type=float)
@click.argument("ty", type=float)
def cmd_drag_and_drop(duration, fx, fy, tx, ty):
    """Drag from (FX, FY) to (TX, TY). Coords can be 0-1 (relative) or pixels."""
    u2_code = f"d.drag_and_drop({fx}, {fy}, {tx}, {ty}, duration={duration})"
    backend = connect_backend()
    backend.drag_and_drop(fx, fy, tx, ty, duration=duration)
    output_result(None, u2_code)


@click.command("zoom")
@click.option("--center-x", required=True, type=float, help="Zoom center X coordinate (0-1 relative or pixels)")
@click.option("--center-y", required=True, type=float, help="Zoom center Y coordinate (0-1 relative or pixels)")
@click.option(
    "--percent",
    required=True,
    type=float,
    help="Positive values zoom in, negative values zoom out; absolute value must be 1-100.",
)
def cmd_zoom(center_x, center_y, percent):
    """Zoom around the UI element covering the given center point."""
    _validate_zoom_percent(percent)
    u2_code = f"d.zoom(center_x={center_x}, center_y={center_y}, percent={percent})"
    backend = connect_backend()
    backend.zoom(center_x, center_y, percent=percent)
    output_result(None, u2_code)


@click.command("send-keys")
@click.option("--no-clear", is_flag=True, default=False, help="Don't clear before typing")
@click.argument("text")
def cmd_send_keys(no_clear, text):
    """Type text into the currently focused input field."""
    clear = not no_clear
    u2_code = f"d.send_keys({text!r}, clear={clear})"
    backend = connect_backend()
    backend.send_keys(text, clear=clear)
    output_result(None, u2_code)


# ---------------------------------------------------------------------------
# Notifications & system UI
# ---------------------------------------------------------------------------


@click.command("open-notification")
def cmd_open_notification():
    """Pull down the notification shade."""
    u2_code = "d.open_notification()"
    backend = connect_backend()
    backend.open_notification()
    extra = None
    if getattr(backend, "platform", None) == "harmony":
        extra = _harmony_partial_extra(
            "Harmony open-notification currently uses a best-effort gesture recipe with desktop-state retry, but without strict panel-state verification.",
            verification="best_effort",
        )
    output_result(None, u2_code, extra=extra)


@click.command("open-quick-settings")
def cmd_open_quick_settings():
    """Pull down the quick settings panel."""
    u2_code = "d.open_quick_settings()"
    backend = connect_backend()
    backend.open_quick_settings()
    extra = None
    if getattr(backend, "platform", None) == "harmony":
        extra = _harmony_partial_extra(
            "Harmony open-quick-settings currently uses a best-effort gesture recipe without panel-state verification.",
            verification="best_effort",
        )
    output_result(None, u2_code, extra=extra)


@click.command("open-url")
@click.argument("url")
def cmd_open_url(url):
    """Open a URL in the default browser or system handler."""
    u2_code = f"d.open_url({url!r})"
    backend = connect_backend()
    backend.open_url(url)
    output_result(None, u2_code)


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------


@click.command("shell")
@click.option("--timeout", default=60, type=int, help="Command timeout in seconds")
@click.argument("cmd", nargs=-1, required=True)
def cmd_shell(timeout, cmd):
    """Run a shell command on the device.

    Example: u2cli shell ls /sdcard
    """
    cmd_str = " ".join(cmd)
    u2_code = f"d.shell({cmd_str!r}, timeout={timeout})"
    backend = connect_backend()
    resp = backend.shell(cmd_str, timeout=timeout)
    output_result(
        {"output": resp.output, "exit_code": resp.exit_code},
        u2_code,
    )


# ---------------------------------------------------------------------------
# Current app
# ---------------------------------------------------------------------------


@click.command("current-app")
def cmd_current_app():
    """Show the current foreground app info (package/bundle and activity/ability when available)."""
    u2_code = "d.app_current()"
    backend = connect_backend()
    info = backend.current_app()
    output_result(info, u2_code)


@click.command("playback-info")
@click.option("--package", default=None, help="Prefer playback session for this package when supported")
def cmd_playback_info(package):
    """Show media playback info using `dumpsys media_session` on Android or `AVSessionService` hidumper on Harmony."""
    backend = connect_backend()
    if getattr(backend, "platform", None) == "harmony":
        u2_code = "d.shell(\"hidumper -s AVSessionService -a '-show_session_info'\")"
    else:
        u2_code = "d.shell('dumpsys media_session')"
    info = backend.playback_info(package=package)
    output_result(info, u2_code)


@click.command("media-control")
@click.argument(
    "action",
    type=click.Choice(["play", "pause", "play-pause", "next", "previous", "stop"]),
)
def cmd_media_control(action):
    """Control media playback when the backend exposes a reliable control path.

    On Harmony, `play`, `pause`, `play-pause`, `next`, and `previous` are
    verified end to end through the zero-install `uitest uiInput keyEvent` path.
    `stop` is dispatched too, but tested players may interpret it as a pause-like
    transition rather than a strict stopped state.
    """
    u2_code_map = {
        "play-pause": "d.press(85)",
        "stop": "d.press(86)",
        "next": "d.press(87)",
        "previous": "d.press(88)",
        "play": "d.press(126)",
        "pause": "d.press(127)",
    }
    ctx = click.get_current_context(silent=True)
    platform = resolve_platform(ctx.obj.get("platform") if ctx is not None and isinstance(ctx.obj, dict) else None)
    serial = ctx.obj.get("serial") if ctx is not None and isinstance(ctx.obj, dict) else None

    if platform == "harmony":
        try:
            harmony_u2_code = run_harmony_media_control_if_available(action, serial=serial)
            if harmony_u2_code is not None:
                output_result(None, harmony_u2_code, extra={"action": action})
                return
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        raise click.ClickException(
            "Harmony media-control is unavailable on this device: the built-in zero-install "
            "uitest uiInput keyEvent path was not available."
        )

    backend = connect_backend()
    try:
        backend.media_control(action)
    except NotImplementedError as exc:
        raise click.ClickException(str(exc)) from exc
    output_result(None, u2_code_map[action], extra={"action": action})
