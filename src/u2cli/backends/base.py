"""Backend protocols for u2cli."""

from __future__ import annotations

from typing import Any, Optional, Protocol


class ElementHandle(Protocol):
    """Minimal element handle used by the stage-1 migrated commands."""

    def click(self, *, timeout: float = 3.0) -> None:
        """Click the selected element."""

    def long_click(self, *, duration: float = 0.5, timeout: float = 3.0) -> None:
        """Long-click the selected element."""

    def get_text(self, *, timeout: float = 3.0) -> str:
        """Read text from the selected element."""

    def set_text(self, text: str, *, timeout: float = 3.0) -> None:
        """Set text on the selected element."""

    def clear_text(self, *, timeout: float = 3.0) -> None:
        """Clear text on the selected element."""

    def exists(self, *, timeout: float = 0.0) -> bool:
        """Check whether the selected element exists."""

    def wait(self, *, timeout: float = 3.0, gone: bool = False) -> Any:
        """Wait for the selected element to appear or disappear."""

    def info(self) -> Any:
        """Return element information."""

    def swipe(self, direction: str, *, steps: int = 10) -> None:
        """Swipe the selected element."""

    def scroll(
        self,
        *,
        direction: str,
        action: str,
        max_swipes: int | None = None,
        to_text: str | None = None,
    ) -> None:
        """Scroll the selected element."""

    def pinch_in(self, *, percent: float = 100.0) -> None:
        """Pinch in on the selected element."""

    def pinch_out(self, *, percent: float = 100.0) -> None:
        """Pinch out on the selected element."""

    def drag_to(self, target: "ElementHandle", *, duration: float = 0.5) -> None:
        """Drag the selected element to another element."""


class LocatorHandle(Protocol):
    """Minimal locator handle used by migrated XPath-style commands."""

    def click(self, *, timeout: float = 3.0) -> None:
        """Click the located element."""

    def get_text(self) -> str:
        """Read text from the located element."""

    def exists(self) -> bool:
        """Check whether the located element exists."""

    def set_text(self, text: str) -> None:
        """Set text on the located element."""


class AutomationBackend(Protocol):
    """Minimal backend interface used in the stage-1 refactor."""

    platform: str
    backend_name: str
    serial: Optional[str]

    def raw_device(self) -> Any:
        """Return the wrapped driver/device instance."""

    def select(self, selector: dict[str, Any]) -> ElementHandle:
        """Return a backend-specific element handle for the selector."""

    def locate(self, strategy: str, value: str) -> LocatorHandle:
        """Return a backend-specific handle for an already-resolved locator."""

    def screenshot(self) -> Any:
        """Capture a screenshot image object."""

    def window_size(self) -> tuple[int, int]:
        """Return screen size as width, height."""

    def shell(self, command: str, *, timeout: int = 60) -> Any:
        """Run a shell command on the target device."""

    def current_app(self) -> Any:
        """Return current foreground app info."""

    def playback_info(self, *, package: str | None = None) -> Any:
        """Return structured media playback state when the backend supports it."""

    def media_control(self, action: str) -> None:
        """Control media playback when the backend supports it."""

    def device_info(self) -> Any:
        """Return device info."""

    def ui_info(self) -> Any:
        """Return UI/device runtime info."""

    def dump_hierarchy_xml(self, *, compressed: bool = False, max_depth: int | None = None) -> str:
        """Return raw hierarchy XML from the backend."""

    def screen_on(self) -> None:
        """Wake the screen."""

    def screen_off(self) -> None:
        """Sleep the screen."""

    def get_orientation(self) -> Any:
        """Return current orientation."""

    def set_orientation(self, orientation: str) -> None:
        """Set current orientation."""

    def press(self, key: Any) -> None:
        """Press hardware or soft key."""

    def swipe(
        self,
        fx: float,
        fy: float,
        tx: float,
        ty: float,
        *,
        duration: float | None = None,
        steps: int | None = None,
    ) -> None:
        """Swipe across the screen."""

    def click(self, x: float, y: float) -> None:
        """Click at coordinates."""

    def swipe_ext(self, direction: str, *, scale: float = 0.8) -> None:
        """Perform high-level directional swipe."""

    def double_click(self, x: float, y: float, *, duration: float = 0.1) -> None:
        """Double-click at coordinates."""

    def long_click(self, x: float, y: float, *, duration: float = 0.5) -> None:
        """Long-click at coordinates."""

    def drag_and_drop(self, fx: float, fy: float, tx: float, ty: float, *, duration: float = 0.5) -> None:
        """Drag from one coordinate to another."""

    def zoom(self, center_x: float, center_y: float, *, percent: float) -> None:
        """Zoom around the UI element that covers the given center point."""

    def send_keys(self, text: str, *, clear: bool = True) -> None:
        """Type text into the current field."""

    def open_notification(self) -> None:
        """Open the notification shade."""

    def open_quick_settings(self) -> None:
        """Open the quick settings panel."""

    def open_url(self, url: str) -> None:
        """Open a URL."""

    def app_start(self, package: str, **kwargs: Any) -> None:
        """Start an app."""

    def app_stop(self, package: str) -> None:
        """Stop an app."""

    def app_stop_all(self) -> None:
        """Stop all apps where supported."""

    def app_clear(self, package: str) -> None:
        """Clear app data."""

    def app_install(self, apk: str) -> None:
        """Install an app artifact."""

    def app_uninstall(self, package: str) -> Any:
        """Uninstall an app."""

    def app_info(self, package: str) -> Any:
        """Return app metadata."""

    def app_list(self, pkg_filter: str = "") -> Any:
        """List installed apps."""

    def app_list_running(self) -> Any:
        """List running apps."""

    def app_wait(self, package: str, *, timeout: float = 20.0, front: bool = False) -> Any:
        """Wait for an app to start or enter foreground."""
