"""u2cli - Command-line interface for uiautomator2.

Each command outputs the corresponding uiautomator2 Python code so
AI agents and users can learn or replay the interaction.

Command groups:
  element   - Interact with UI elements (click, get-text, set-text, exists, ...)
  xpath     - XPath-based element interaction
  device    - Device-level actions (screenshot, swipe, press, info, ...)
  app       - App management (start, stop, install, list, ...)
"""

from __future__ import annotations

import json
import shlex
import sys

import click

from u2cli.daemon import (
    daemon_status,
    read_log_tail,
    restart_daemon,
    run_via_daemon,
    should_delegate_command,
    start_daemon,
    stop_daemon,
)

# Element commands
from u2cli.element import (
    cmd_click,
    cmd_clear_text,
    cmd_element_info,
    cmd_exists,
    cmd_get_text,
    cmd_long_click,
    cmd_scroll,
    cmd_set_text,
    cmd_swipe_element,
    cmd_wait,
    cmd_xpath_click,
    cmd_xpath_exists,
    cmd_xpath_get_text,
    cmd_xpath_set_text,
)

# Screen / device commands
from u2cli.screen import (
    cmd_click_coord,
    cmd_current_app,
    cmd_device_info,
    cmd_double_click,
    cmd_dump_hierarchy,
    cmd_long_click_coord,
    cmd_media_control,
    cmd_open_notification,
    cmd_open_quick_settings,
    cmd_open_url,
    cmd_orientation,
    cmd_playback_info,
    cmd_press,
    cmd_screen_off,
    cmd_screen_on,
    cmd_screenshot,
    cmd_send_keys,
    cmd_shell,
    cmd_swipe,
    cmd_swipe_ext,
    cmd_ui_info,
    cmd_window_size,
)

# App commands
from u2cli.app import (
    cmd_app_clear,
    cmd_app_info,
    cmd_app_install,
    cmd_app_list,
    cmd_app_list_running,
    cmd_app_start,
    cmd_app_stop,
    cmd_app_uninstall,
    cmd_app_wait,
)


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option()
@click.option("-s", "--serial", default=None, envvar="ANDROID_SERIAL", help="Target device serial (or set ANDROID_SERIAL)")
@click.option(
    "--platform",
    type=click.Choice(["android", "harmony", "auto"]),
    default="auto",
    show_default=True,
    help="Backend platform: android, harmony, or auto (auto resolves to android; harmony requires explicit opt-in)",
)
@click.option("--no-daemon", is_flag=True, help="Run in-process instead of routing the command through the background daemon")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.pass_context
def cli(ctx, serial, platform, no_daemon, output_json):
    """u2cli — uiautomator2 command-line interface.

    Every command prints the equivalent uiautomator2 Python code alongside
    its result, making it easy to build automation scripts.

    \b
    Examples:
      u2cli click --text Settings
      u2cli get-text --resource-id com.android.settings:id/title
      u2cli screenshot screen.png
      u2cli press back
      u2cli app-start com.android.settings
      u2cli xpath-click "//android.widget.Button[@text='OK']"
      u2cli shell "pm list packages -3"
    """
    ctx.ensure_object(dict)
    ctx.obj["serial"] = serial
    ctx.obj["platform"] = platform
    ctx.obj["no_daemon"] = no_daemon
    ctx.obj["output_json"] = output_json

    if not no_daemon and should_delegate_command(invoked_subcommand=ctx.invoked_subcommand):
        exit_code = run_via_daemon(serial=serial, platform=platform, argv=sys.argv[1:])
        ctx.exit(exit_code)


@click.command("repl")
@click.pass_context
def cmd_repl(ctx):
    """Run interactive u2cli commands without reconnecting each time.

    Type commands exactly like normal u2cli subcommands, for example:
      click --text Settings
      get-text --resource-id com.android.settings:id/title

    Type "exit" or "quit" to leave.
    """
    click.echo('u2cli repl started. Type "exit" or "quit" to leave.')
    while True:
        try:
            line = input("u2cli> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break

        if not line:
            continue
        if line in {"exit", "quit"}:
            break

        try:
            args = shlex.split(line)
        except ValueError as e:
            click.echo(f"Parse error: {e}")
            continue

        if not args:
            continue
        if args[0] == "repl":
            click.echo("Nested repl is not supported.")
            continue

        try:
            cli.main(args=args, standalone_mode=False, obj=ctx.obj)
        except click.exceptions.Exit:
            pass
        except click.ClickException as e:
            click.echo(json.dumps({"error": e.format_message(), "type": type(e).__name__}, ensure_ascii=False), err=True)
        except Exception as e:
            click.echo(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False), err=True)


@click.group("daemon")
def daemon_group():
    """Manage the background u2cli daemon for the current platform/serial target."""


@daemon_group.command("start")
@click.option(
    "--full-output-log/--no-full-output-log",
    "full_output_log",
    default=None,
    help="Write full command stdout/stderr into daemon log file",
)
@click.pass_context
def cmd_daemon_start(ctx, full_output_log):
    """Start daemon for the current platform/serial target."""
    ok, message = start_daemon(
        ctx.obj.get("serial"),
        platform=ctx.obj.get("platform"),
        full_output_log=full_output_log,
    )
    if ctx.obj.get("output_json"):
        click.echo(json.dumps({"ok": ok, "message": message}, ensure_ascii=False))
    else:
        click.echo(message)
    if not ok:
        raise click.ClickException(message)


@daemon_group.command("stop")
@click.pass_context
def cmd_daemon_stop(ctx):
    """Stop daemon for the current platform/serial target."""
    ok, message = stop_daemon(ctx.obj.get("serial"), platform=ctx.obj.get("platform"))
    if ctx.obj.get("output_json"):
        click.echo(json.dumps({"ok": ok, "message": message}, ensure_ascii=False))
    else:
        click.echo(message)
    if not ok:
        raise click.ClickException(message)


@daemon_group.command("restart")
@click.option(
    "--full-output-log/--no-full-output-log",
    "full_output_log",
    default=None,
    help="Write full command stdout/stderr into daemon log file",
)
@click.pass_context
def cmd_daemon_restart(ctx, full_output_log):
    """Restart daemon for the current platform/serial target."""
    ok, message = restart_daemon(
        ctx.obj.get("serial"),
        platform=ctx.obj.get("platform"),
        full_output_log=full_output_log,
    )
    if ctx.obj.get("output_json"):
        click.echo(json.dumps({"ok": ok, "message": message}, ensure_ascii=False))
    else:
        click.echo(message)
    if not ok:
        raise click.ClickException(message)


@daemon_group.command("status")
@click.pass_context
def cmd_daemon_status(ctx):
    """Show daemon status for the current platform/serial target."""
    status = daemon_status(ctx.obj.get("serial"), platform=ctx.obj.get("platform"))
    if ctx.obj.get("output_json"):
        click.echo(json.dumps(status, ensure_ascii=False))
        return

    click.echo(f"running: {status.get('running')}")
    click.echo(f"socket: {status.get('socket')}")
    click.echo(f"pid_file: {status.get('pid_file')}")
    click.echo(f"log_file: {status.get('log_file')}")
    click.echo(f"full_output_log: {status.get('full_output_log', False)}")
    if "code_fingerprint" in status:
        click.echo(f"code_fingerprint: {status['code_fingerprint']}")
    if "started_at" in status:
        click.echo(f"started_at: {status['started_at']}")
    if "last_request_at" in status:
        click.echo(f"last_request_at: {status['last_request_at']}")
    if "request_count" in status:
        click.echo(f"request_count: {status['request_count']}")
    if "backend_cached" in status:
        click.echo(f"backend_cached: {status['backend_cached']}")
    if "active_device_id" in status:
        click.echo(f"active_device_id: {status['active_device_id']}")
    if "pid" in status:
        click.echo(f"pid: {status['pid']}")


@daemon_group.command("logs")
@click.option("--lines", default=200, type=int, help="Number of latest log lines")
@click.pass_context
def cmd_daemon_logs(ctx, lines):
    """Show daemon log tail for the current platform/serial target."""
    text = read_log_tail(ctx.obj.get("serial"), lines=lines, platform=ctx.obj.get("platform"))
    if not text:
        click.echo("No log entries yet.")
        return
    click.echo(text, nl=False)


# ---------------------------------------------------------------------------
# Element commands (top-level — most common operations)
# ---------------------------------------------------------------------------

cli.add_command(cmd_click, name="click")
cli.add_command(cmd_long_click, name="long-click")
cli.add_command(cmd_get_text, name="get-text")
cli.add_command(cmd_set_text, name="set-text")
cli.add_command(cmd_clear_text, name="clear-text")
cli.add_command(cmd_exists, name="exists")
cli.add_command(cmd_wait, name="wait")
cli.add_command(cmd_element_info, name="element-info")
cli.add_command(cmd_swipe_element, name="swipe-element")
cli.add_command(cmd_scroll, name="scroll")

# XPath commands
cli.add_command(cmd_xpath_click, name="xpath-click")
cli.add_command(cmd_xpath_exists, name="xpath-exists")
cli.add_command(cmd_xpath_get_text, name="xpath-get-text")
cli.add_command(cmd_xpath_set_text, name="xpath-set-text")

# ---------------------------------------------------------------------------
# Device / screen commands
# ---------------------------------------------------------------------------

cli.add_command(cmd_screenshot, name="screenshot")
cli.add_command(cmd_dump_hierarchy, name="dump-hierarchy")
cli.add_command(cmd_device_info, name="device-info")
cli.add_command(cmd_ui_info, name="ui-info")
cli.add_command(cmd_window_size, name="window-size")
cli.add_command(cmd_screen_on, name="screen-on")
cli.add_command(cmd_screen_off, name="screen-off")
cli.add_command(cmd_orientation, name="orientation")
cli.add_command(cmd_press, name="press")
cli.add_command(cmd_swipe, name="swipe")
cli.add_command(cmd_swipe_ext, name="swipe-ext")
cli.add_command(cmd_click_coord, name="click-coord")
cli.add_command(cmd_double_click, name="double-click")
cli.add_command(cmd_long_click_coord, name="long-click-coord")
cli.add_command(cmd_send_keys, name="send-keys")
cli.add_command(cmd_open_notification, name="open-notification")
cli.add_command(cmd_open_quick_settings, name="open-quick-settings")
cli.add_command(cmd_open_url, name="open-url")
cli.add_command(cmd_shell, name="shell")
cli.add_command(cmd_current_app, name="current-app")
cli.add_command(cmd_playback_info, name="playback-info")
cli.add_command(cmd_media_control, name="media-control")

# ---------------------------------------------------------------------------
# App management commands
# ---------------------------------------------------------------------------

cli.add_command(cmd_app_start, name="app-start")
cli.add_command(cmd_app_stop, name="app-stop")
cli.add_command(cmd_app_clear, name="app-clear")
cli.add_command(cmd_app_install, name="app-install")
cli.add_command(cmd_app_uninstall, name="app-uninstall")
cli.add_command(cmd_app_info, name="app-info")
cli.add_command(cmd_app_list, name="app-list")
cli.add_command(cmd_app_list_running, name="app-list-running")
cli.add_command(cmd_app_wait, name="app-wait")
cli.add_command(cmd_repl, name="repl")
cli.add_command(daemon_group, name="daemon")


def main():
    try:
        cli(standalone_mode=False)
    except click.exceptions.Exit:
        pass
    except click.ClickException as e:
        click.echo(json.dumps({"error": e.format_message(), "type": type(e).__name__}, ensure_ascii=False), err=True)
        sys.exit(e.exit_code)
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False), err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
