"""Real-device smoke checks for u2cli backends."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

import click

from u2cli.device import connect_backend


def _run_step(name: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"name": name, "ok": True, "result": action()}
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "error": str(exc),
            "type": type(exc).__name__,
        }


@click.command("u2cli-smoke")
@click.option("-s", "--serial", default=None, help="Target device serial")
@click.option("--platform", type=click.Choice(["android", "harmony"]), required=True, help="Backend platform")
@click.option("--screenshot", default=None, help="Optional path to save a smoke screenshot")
@click.option("--json", "output_json", is_flag=True, help="Emit JSON output")
def smoke_cli(serial: str | None, platform: str, screenshot: str | None, output_json: bool) -> None:
    """Run a small real-device smoke suite against a connected target."""
    backend = connect_backend(serial, platform=platform)
    steps: list[dict[str, Any]] = []

    steps.append(_run_step("device_info", backend.device_info))
    steps.append(_run_step("window_size", lambda: {"width": backend.window_size()[0], "height": backend.window_size()[1]}))
    steps.append(_run_step("current_app", backend.current_app))

    def capture_screenshot() -> dict[str, Any]:
        image = backend.screenshot()
        result = {"resolution": {"width": image.size[0], "height": image.size[1]}}
        if screenshot:
            abs_path = os.path.abspath(screenshot)
            image.save(abs_path)
            result["saved_to"] = abs_path
        return result

    steps.append(_run_step("screenshot", capture_screenshot))
    steps.append(_run_step("dump_hierarchy", lambda: {"xml_length": len(backend.dump_hierarchy_xml())}))

    steps.append(_run_step("playback_info", backend.playback_info))

    payload = {
        "ok": all(step["ok"] for step in steps),
        "platform": platform,
        "serial": serial,
        "steps": steps,
    }

    if output_json:
        click.echo(json.dumps(payload, ensure_ascii=False))
    else:
        click.echo(f"platform: {platform}")
        click.echo(f"serial: {serial or '<default>'}")
        for step in steps:
            if step["ok"]:
                click.echo(f"PASS {step['name']}: {json.dumps(step['result'], ensure_ascii=False)}")
            else:
                click.echo(f"FAIL {step['name']}: {step['type']}: {step['error']}")

    raise SystemExit(0 if payload["ok"] else 1)


def main() -> None:
    try:
        smoke_cli(standalone_mode=False)
    except click.exceptions.Exit:
        raise
    except click.ClickException as exc:
        click.echo(json.dumps({"error": exc.format_message(), "type": type(exc).__name__}, ensure_ascii=False), err=True)
        sys.exit(exc.exit_code)
    except Exception as exc:
        click.echo(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), err=True)
        sys.exit(1)