"""Minimal HDC transport helpers for Harmony backend bootstrap."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


HDC_BIN_ENV = "HDC_BIN"


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


def connect_harmony_driver(serial: Optional[str] = None):
    Driver = _load_hmdriver2_driver()
    ensure_hdc_available()
    resolved_serial = serial or resolve_default_target()
    return Driver(resolved_serial)