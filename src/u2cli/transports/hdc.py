"""Minimal HDC transport helpers for Harmony backend bootstrap."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional


HDC_BIN_ENV = "HDC_BIN"
_HARMONY_TARGET_RECOVERY_TIMEOUT = 3.0
_HARMONY_TARGET_RECOVERY_INTERVAL = 0.5
_HARMONY_TARGET_MISSING_ERROR_MARKERS = (
    "no devices found",
    "device not found",
    "device not founded or connected",
)


def hdc_executable() -> str:
    return os.getenv(HDC_BIN_ENV, "hdc")


def ensure_hdc_available() -> str:
    executable = hdc_executable()
    if shutil.which(executable):
        return executable
    raise RuntimeError(
        f"Harmony support requires the HDC executable ({executable!r}) to be available in PATH or via {HDC_BIN_ENV}."
    )


def list_targets() -> list[str]:
    executable = ensure_hdc_available()
    proc = subprocess.run(
        [executable, "list", "targets"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "failed to list HDC targets")

    targets = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.lower() == "empty":
            continue
        targets.append(line)
    return targets


def resolve_default_target() -> str:
    targets = list_targets()
    if not targets:
        raise RuntimeError("no Harmony target detected via hdc")
    if len(targets) > 1:
        raise RuntimeError("more than one Harmony target detected; use --serial to choose one")
    return targets[0]


def run_hdc_shell(command_argv: list[str], *, serial: Optional[str] = None, timeout: Optional[float] = None):
    executable = ensure_hdc_available()
    argv = [executable]
    if serial:
        argv.extend(["-t", serial])
    argv.extend(["shell", *command_argv])
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _load_hmdriver2_driver() -> type:
    try:
        from hmdriver2.driver import Driver
    except ImportError as exc:
        raise RuntimeError(
            "Harmony support requires hmdriver2. Install the optional dependency set with: pip install 'uiautomator2-cli[harmony]'"
        ) from exc
    return Driver


def _reset_hmdriver2_driver_instance(Driver: type, serial: str) -> None:
    instances = getattr(Driver, "_instance", None)
    if not isinstance(instances, dict):
        return

    cached = instances.pop(serial, None)
    if cached is None:
        return

    client = getattr(cached, "_client", None)
    release = getattr(client, "release", None)
    if callable(release):
        release()


def _is_harmony_target_missing_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _HARMONY_TARGET_MISSING_ERROR_MARKERS)


def _wait_for_harmony_target(
    serial: str,
    *,
    timeout: float = _HARMONY_TARGET_RECOVERY_TIMEOUT,
    interval: float = _HARMONY_TARGET_RECOVERY_INTERVAL,
) -> None:
    deadline = time.monotonic() + max(0.0, timeout)

    while True:
        try:
            targets = list_targets()
        except RuntimeError:
            targets = []

        if serial in targets:
            return

        if time.monotonic() >= deadline:
            raise RuntimeError(f"Harmony target [{serial}] did not reappear via hdc within {timeout:.1f}s")

        time.sleep(interval)


def connect_harmony_driver(serial: Optional[str] = None):
    Driver = _load_hmdriver2_driver()
    ensure_hdc_available()
    resolved_serial = serial or resolve_default_target()
    _wait_for_harmony_target(resolved_serial)
    _reset_hmdriver2_driver_instance(Driver, resolved_serial)

    try:
        return Driver(resolved_serial)
    except Exception as exc:
        if not _is_harmony_target_missing_error(exc):
            raise

        _wait_for_harmony_target(resolved_serial)
        _reset_hmdriver2_driver_instance(Driver, resolved_serial)
        return Driver(resolved_serial)