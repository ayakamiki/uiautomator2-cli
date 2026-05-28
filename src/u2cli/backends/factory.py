"""Backend factory helpers for u2cli."""

from __future__ import annotations

from typing import Any, Optional

from u2cli.backends.android_u2 import AndroidU2Backend
from u2cli.backends.harmony_hm import HarmonyHmBackend
from u2cli.backends.base import AutomationBackend


def resolve_platform(platform: Optional[str]) -> str:
    """Normalize the requested platform.

    ``auto`` still resolves to Android to preserve existing behavior while
    Harmony support is introduced behind an explicit platform opt-in.
    """

    if platform in {None, "", "auto", "android"}:
        return "android"
    if platform == "harmony":
        return "harmony"
    raise ValueError(f"unsupported platform: {platform}")


def create_backend(platform: Optional[str], *, serial: Optional[str], raw_device: Any) -> AutomationBackend:
    """Wrap a concrete driver/device instance in the appropriate backend."""

    resolved_platform = resolve_platform(platform)
    if resolved_platform == "android":
        return AndroidU2Backend(device=raw_device, serial=serial)
    if resolved_platform == "harmony":
        return HarmonyHmBackend(device=raw_device, serial=serial)
    raise ValueError(f"unsupported platform: {resolved_platform}")