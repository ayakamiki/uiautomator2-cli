"""Device connection management for u2cli."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional

import adbutils
import click
import uiautomator2 as u2


_DEVICE_CACHE: dict[str, u2.Device] = {}
_DEFAULT_DEVICE_SERIAL: Optional[str] = None
_LOGGER = logging.getLogger("u2cli.device")


def _cache_key(serial: Optional[str]) -> str:
    return serial or "__default__"


def _resolve_serial(serial: Optional[str]) -> Optional[str]:
    if serial is not None:
        return serial

    ctx = click.get_current_context(silent=True)
    if ctx is not None and isinstance(ctx.obj, dict):
        return ctx.obj.get("serial")
    return None


def clear_cached_device(serial: Optional[str] = None) -> None:
    global _DEFAULT_DEVICE_SERIAL

    if serial is None:
        if _DEFAULT_DEVICE_SERIAL is not None:
            _LOGGER.info("clear sticky default device device_id=%r", _DEFAULT_DEVICE_SERIAL)
        _DEFAULT_DEVICE_SERIAL = None
        _DEVICE_CACHE.pop(_cache_key(None), None)
        return

    _DEVICE_CACHE.pop(_cache_key(serial), None)
    if _DEFAULT_DEVICE_SERIAL == serial:
        _LOGGER.info("clear sticky default device device_id=%r", _DEFAULT_DEVICE_SERIAL)
        _DEFAULT_DEVICE_SERIAL = None
        _DEVICE_CACHE.pop(_cache_key(None), None)


def _current_unique_serial() -> str:
    return adbutils.adb.device().serial


def default_device_serial() -> Optional[str]:
    return _DEFAULT_DEVICE_SERIAL


def connect_device(serial: Optional[str] = None) -> u2.Device:
    """Connect to a device.

    *serial* takes priority. If not given, falls back to the serial stored in
    the current Click context object (set by the top-level ``cli`` group).
    """
    global _DEFAULT_DEVICE_SERIAL

    requested_serial = _resolve_serial(serial)
    cache_serial = requested_serial

    # Daemon mode retries once to handle transient ADB/transport hiccups.
    max_attempts = 2 if os.getenv("U2CLI_IN_DAEMON") == "1" else 1
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        selected_serial = requested_serial
        try:
            if selected_serial is None:
                if _DEFAULT_DEVICE_SERIAL is None:
                    _DEFAULT_DEVICE_SERIAL = _current_unique_serial()
                    _LOGGER.info("bind sticky default device device_id=%r", _DEFAULT_DEVICE_SERIAL)
                selected_serial = _DEFAULT_DEVICE_SERIAL
                cache_serial = None

            cached = _DEVICE_CACHE.get(_cache_key(cache_serial))
            if cached is not None:
                _LOGGER.info(
                    "use cached device device_id=%r requested_serial=%r selected_serial=%r cache_serial=%r",
                    selected_serial,
                    requested_serial,
                    selected_serial,
                    cache_serial,
                )
                return cached

            _LOGGER.info(
                "connect attempt=%s/%s device_id=%r requested_serial=%r selected_serial=%r cache_serial=%r",
                attempt,
                max_attempts,
                selected_serial,
                requested_serial,
                selected_serial,
                cache_serial,
            )
            if selected_serial:
                d = u2.connect(selected_serial)
            else:
                d = u2.connect()
            _DEVICE_CACHE[_cache_key(cache_serial)] = d
            _LOGGER.info(
                "connect success device_id=%r requested_serial=%r selected_serial=%r cache_serial=%r",
                selected_serial,
                requested_serial,
                selected_serial,
                cache_serial,
            )
            return d
        except Exception as e:
            last_error = e
            _LOGGER.warning(
                "connect failed attempt=%s device_id=%r requested_serial=%r selected_serial=%r cache_serial=%r error=%s",
                attempt,
                selected_serial,
                requested_serial,
                selected_serial,
                cache_serial,
                e,
            )
            clear_cached_device(cache_serial)

    click.echo(
        json.dumps({"error": str(last_error), "type": type(last_error).__name__}, ensure_ascii=False),
        err=True,
    )
    sys.exit(1)


def build_selector_repr(kwargs: dict) -> str:
    """Build a Python-style selector expression from kwargs."""
    parts = []
    for k, v in kwargs.items():
        if isinstance(v, str):
            parts.append(f"{k}={v!r}")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def output_result(
    result: object,
    u2_code: str,
    output_json: Optional[bool] = None,
    extra: Optional[dict] = None,
) -> None:
    """Output result in human-readable or JSON format, always including u2 code."""
    if output_json is None:
        ctx = click.get_current_context(silent=True)
        if ctx is not None and isinstance(ctx.obj, dict):
            output_json = ctx.obj.get("output_json", False)
        else:
            output_json = False

    data: dict = {"u2_code": u2_code}
    if extra:
        data.update(extra)
    if result is not None:
        data["result"] = result

    if output_json:
        click.echo(json.dumps(data, default=str, ensure_ascii=False))
    else:
        click.echo(f"u2_code: {u2_code}")
        if extra:
            for k, v in extra.items():
                click.echo(f"{k}: {v}")
        if result is not None:
            if isinstance(result, (dict, list)):
                click.echo(json.dumps(result, default=str, indent=2, ensure_ascii=False))
            else:
                click.echo(f"result: {result}")
