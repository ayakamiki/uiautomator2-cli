"""App management commands for u2cli.

Commands for installing, launching, stopping, and managing apps.
"""

from __future__ import annotations

import click

from u2cli.device import connect_backend, output_result


def _harmony_partial_extra(note: str) -> dict[str, object]:
    return {
        "partial": True,
        "support_level": "partial",
        "note": note,
    }


def _ensure_harmony_app_artifact_supported(backend, command_name: str) -> None:
    if getattr(backend, "platform", None) == "harmony":
        raise click.ClickException(
            f"{command_name} is not yet supported on Harmony: the current CLI has not normalized the artifact model "
            "between Android APK flows and Harmony HAP/package flows, so install/uninstall remains gated until the "
            "Stage-3-style app service lands."
        )


@click.command("app-start")
@click.option("--activity", default=None, help="Specific activity/ability to launch when supported")
@click.option("--wait", is_flag=True, default=False, help="Wait for app to launch")
@click.option("--stop", is_flag=True, default=False, help="Stop app before launching")
@click.argument("package")
def cmd_app_start(activity, wait, stop, package):
    """Start (launch) an app by package/bundle identifier."""
    parts = [repr(package)]
    if activity:
        parts.append(f"activity={activity!r}")
    if wait:
        parts.append("wait=True")
    if stop:
        parts.append("stop=True")
    u2_code = f"d.app_start({', '.join(parts)})"

    backend = connect_backend()
    kw: dict = {}
    if activity:
        kw["activity"] = activity
    if wait:
        kw["wait"] = True
    if stop:
        kw["stop"] = True
    backend.app_start(package, **kw)
    output_result(None, u2_code)


@click.command("app-stop")
@click.option("--all", "stop_all", is_flag=True, default=False, help="Stop all third-party apps")
@click.argument("package", required=False)
def cmd_app_stop(stop_all, package):
    """Force-stop an app (or all third-party apps with --all)."""
    backend = connect_backend()
    if stop_all:
        u2_code = "d.app_stop_all()"
        backend.app_stop_all()
        output_result(None, u2_code)
    elif package:
        u2_code = f"d.app_stop({package!r})"
        backend.app_stop(package)
        output_result(None, u2_code)
    else:
        raise click.UsageError("Provide PACKAGE or use --all.")


@click.command("app-clear")
@click.argument("package")
def cmd_app_clear(package):
    """Clear app data for a package/bundle identifier."""
    u2_code = f"d.app_clear({package!r})"
    backend = connect_backend()
    backend.app_clear(package)
    output_result(None, u2_code)


@click.command("app-install")
@click.argument("apk")
def cmd_app_install(apk):
    """Install an app package from a local path or URL."""
    u2_code = f"d.app_install({apk!r})"
    backend = connect_backend()
    _ensure_harmony_app_artifact_supported(backend, "app-install")
    backend.app_install(apk)
    output_result(None, u2_code)


@click.command("app-uninstall")
@click.argument("package")
def cmd_app_uninstall(package):
    """Uninstall an app by package/bundle identifier."""
    u2_code = f"d.app_uninstall({package!r})"
    backend = connect_backend()
    _ensure_harmony_app_artifact_supported(backend, "app-uninstall")
    result = backend.app_uninstall(package)
    output_result(result, u2_code)


@click.command("app-info")
@click.argument("package")
def cmd_app_info(package):
    """Get app metadata such as version and installation state."""
    u2_code = f"d.app_info({package!r})"
    backend = connect_backend()
    info = backend.app_info(package)
    extra = None
    if getattr(backend, "platform", None) == "harmony":
        extra = _harmony_partial_extra(
            "Harmony app-info currently returns a pre-normalized compatibility payload; the unified app service "
            "schema is still pending."
        )
    output_result(info, u2_code, extra=extra)


@click.command("app-list")
@click.option(
    "--filter",
    "pkg_filter",
    default="",
    help="Filter string for installed app identifiers",
)
def cmd_app_list(pkg_filter):
    """List installed apps."""
    if pkg_filter:
        u2_code = f"d.app_list({pkg_filter!r})"
    else:
        u2_code = "d.app_list()"
    backend = connect_backend()
    packages = backend.app_list(pkg_filter)
    extra = None
    if getattr(backend, "platform", None) == "harmony":
        extra = _harmony_partial_extra(
            "Harmony app-list currently exposes a pre-normalized compatibility view and may differ from the final "
            "cross-platform app inventory semantics."
        )
    output_result(packages, u2_code, extra=extra)


@click.command("app-list-running")
def cmd_app_list_running():
    """List currently running apps."""
    u2_code = "d.app_list_running()"
    backend = connect_backend()
    packages = backend.app_list_running()
    extra = None
    if getattr(backend, "platform", None) == "harmony":
        extra = _harmony_partial_extra(
            "Harmony app-list-running currently reports a reduced compatibility view rather than a normalized running "
            "app model."
        )
    output_result(packages, u2_code, extra=extra)


@click.command("app-wait")
@click.option("--timeout", default=20.0, type=float, help="Timeout in seconds")
@click.option("--front", is_flag=True, default=False, help="Wait until app is in foreground")
@click.argument("package")
def cmd_app_wait(timeout, front, package):
    """Wait until an app is running (or in the foreground with --front)."""
    parts = [repr(package), f"timeout={timeout}"]
    if front:
        parts.append("front=True")
    u2_code = f"d.app_wait({', '.join(parts)})"

    backend = connect_backend()
    pid = backend.app_wait(package, timeout=timeout, front=front)
    output_result(pid, u2_code)
