"""Backend abstractions for u2cli."""

from u2cli.backends.android_u2 import AndroidU2Backend
from u2cli.backends.base import AutomationBackend
from u2cli.backends.factory import create_backend, resolve_platform
from u2cli.backends.harmony_hm import HarmonyHmBackend

__all__ = [
    "AndroidU2Backend",
    "AutomationBackend",
    "HarmonyHmBackend",
    "create_backend",
    "resolve_platform",
]