"""Android backend backed by uiautomator2."""

from __future__ import annotations

import re
from typing import Any, Optional


_PLAYBACK_STATE_NAMES = {
    0: "none",
    1: "stopped",
    2: "paused",
    3: "playing",
    4: "fast_forwarding",
    5: "rewinding",
    6: "buffering",
    7: "error",
    8: "connecting",
    9: "skipping_to_previous",
    10: "skipping_to_next",
    11: "skipping_to_queue_item",
}
_MEDIA_CONTROL_KEYCODES = {
    "play-pause": 85,
    "stop": 86,
    "next": 87,
    "previous": 88,
    "play": 126,
    "pause": 127,
}

_SESSION_HEADER_RE = re.compile(r"^\s+\S+\s+\S+/\S+\s+\(userId=\d+\)$")
_PACKAGE_RE = re.compile(r"^\s+package=(?P<package>.+)$")
_STATE_RE = re.compile(
    r"state=PlaybackState \{state=(?P<code>\d+), position=(?P<position>-?\d+), "
    r"buffered position=(?P<buffered>-?\d+), speed=(?P<speed>-?[0-9.]+)"
)
_METADATA_RE = re.compile(r"^\s+metadata:\s+(?P<body>.+)$")
_DESCRIPTION_RE = re.compile(r"(?:size=\d+,\s*)?description=(?P<description>.+)$")


def _parse_track_description(description: str) -> dict[str, str | None]:
    parts = [part.strip() for part in description.split(",", 2)]
    while len(parts) < 3:
        parts.append(None)
    title, artist, album = parts[:3]
    return {"title": title, "artist": artist, "album": album}


def _parse_media_session_dump(output: str) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in output.splitlines():
        if _SESSION_HEADER_RE.match(line):
            if current and current.get("package"):
                sessions.append(current)
            current = {"session": line.strip(), "state": None, "track": None}
            continue

        if current is None:
            continue

        package_match = _PACKAGE_RE.match(line)
        if package_match:
            current["package"] = package_match.group("package")
            continue

        state_match = _STATE_RE.search(line)
        if state_match:
            code = int(state_match.group("code"))
            current["state"] = {
                "code": code,
                "name": _PLAYBACK_STATE_NAMES.get(code, f"unknown_{code}"),
                "position": int(state_match.group("position")),
                "buffered_position": int(state_match.group("buffered")),
                "speed": float(state_match.group("speed")),
            }
            continue

        metadata_match = _METADATA_RE.match(line)
        if not metadata_match:
            continue

        metadata_body = metadata_match.group("body")
        if metadata_body == "null":
            current["track"] = None
            continue

        description_match = _DESCRIPTION_RE.search(metadata_body)
        if description_match:
            current["track"] = _parse_track_description(description_match.group("description"))

    if current and current.get("package"):
        sessions.append(current)

    return sessions


def _select_playback_session(sessions: list[dict[str, Any]], package: str | None) -> dict[str, Any] | None:
    candidates = [session for session in sessions if session.get("package") == package] if package else sessions
    if not candidates:
        return None

    def rank(session: dict[str, Any]) -> tuple[int, int, int]:
        state_code = (session.get("state") or {}).get("code", -1)
        return (
            1 if state_code == 3 else 0,
            1 if session.get("track") else 0,
            state_code,
        )

    return max(candidates, key=rank)


class AndroidU2Element:
    """Thin wrapper around a uiautomator2 selector object."""

    def __init__(self, element: Any) -> None:
        self._element = element

    def click(self, *, timeout: float = 3.0) -> None:
        self._element.click(timeout=timeout)

    def long_click(self, *, duration: float = 0.5, timeout: float = 3.0) -> None:
        self._element.long_click(duration=duration, timeout=timeout)

    def get_text(self, *, timeout: float = 3.0) -> str:
        return self._element.get_text(timeout=timeout)

    def set_text(self, text: str, *, timeout: float = 3.0) -> None:
        self._element.set_text(text, timeout=timeout)

    def clear_text(self, *, timeout: float = 3.0) -> None:
        self._element.clear_text(timeout=timeout)

    def exists(self, *, timeout: float = 0.0) -> bool:
        if timeout:
            return bool(self._element.exists(timeout=timeout))
        return bool(self._element.exists)

    def wait(self, *, timeout: float = 3.0, gone: bool = False) -> Any:
        if gone:
            return self._element.wait_gone(timeout=timeout)
        return self._element.wait(timeout=timeout)

    def info(self) -> Any:
        return self._element.info

    def swipe(self, direction: str, *, steps: int = 10) -> None:
        self._element.swipe(direction, steps=steps)

    def scroll(
        self,
        *,
        direction: str,
        action: str,
        max_swipes: int | None = None,
        to_text: str | None = None,
    ) -> None:
        if to_text:
            getattr(self._element.scroll, direction).to(text=to_text)
            return
        if max_swipes is not None:
            getattr(getattr(self._element.scroll, direction), action)(max_swipes=max_swipes)
            return
        getattr(getattr(self._element.scroll, direction), action)()


class AndroidU2Locator:
    """Thin wrapper around a uiautomator2 XPath selector object."""

    def __init__(self, xpath_selector: Any) -> None:
        self._xpath_selector = xpath_selector

    def click(self, *, timeout: float = 3.0) -> None:
        self._xpath_selector.click(timeout=timeout)

    def get_text(self) -> str:
        return self._xpath_selector.get_text()

    def exists(self) -> bool:
        return bool(self._xpath_selector.exists)

    def set_text(self, text: str) -> None:
        self._xpath_selector.set_text(text)


class AndroidU2Backend:
    """Thin stage-1 wrapper around a uiautomator2 device instance."""

    platform = "android"
    backend_name = "uiautomator2"

    def __init__(self, device: Any, serial: Optional[str] = None) -> None:
        self._device = device
        self.serial = serial

    def raw_device(self) -> Any:
        return self._device

    def select(self, selector: dict[str, Any]) -> AndroidU2Element:
        return AndroidU2Element(self._device(**selector))

    def locate(self, strategy: str, value: str) -> AndroidU2Locator:
        if strategy != "xpath":
            raise ValueError(f"Android backend does not support locator strategy: {strategy}")
        return AndroidU2Locator(self._device.xpath(value))

    def screenshot(self) -> Any:
        return self._device.screenshot()

    def window_size(self) -> tuple[int, int]:
        return self._device.window_size()

    def shell(self, command: str, *, timeout: int = 60) -> Any:
        return self._device.shell(command, timeout=timeout)

    def current_app(self) -> Any:
        return self._device.app_current()

    def playback_info(self, *, package: str | None = None) -> Any:
        requested_package = package
        if requested_package is None:
            current = self.current_app()
            if isinstance(current, dict):
                requested_package = current.get("package")

        output = str(self.shell("dumpsys media_session").output)
        sessions = _parse_media_session_dump(output)
        selected = _select_playback_session(sessions, requested_package)

        return {
            "source": "media_session",
            "requested_package": requested_package,
            "package": selected.get("package") if selected else requested_package,
            "state": selected.get("state") if selected else None,
            "track": selected.get("track") if selected else None,
        }

    def media_control(self, action: str) -> None:
        try:
            keycode = _MEDIA_CONTROL_KEYCODES[action]
        except KeyError as exc:
            raise ValueError(f"Unsupported media action: {action}") from exc
        self.press(keycode)

    def device_info(self) -> Any:
        return self._device.device_info

    def ui_info(self) -> Any:
        return self._device.info

    def dump_hierarchy_xml(self, *, compressed: bool = False, max_depth: int | None = None) -> str:
        kwargs: dict[str, Any] = {}
        if compressed:
            kwargs["compressed"] = True
        if max_depth is not None:
            kwargs["max_depth"] = max_depth
        return self._device.dump_hierarchy(**kwargs)

    def screen_on(self) -> None:
        self._device.screen_on()

    def screen_off(self) -> None:
        self._device.screen_off()

    def get_orientation(self) -> Any:
        return self._device.orientation

    def set_orientation(self, orientation: str) -> None:
        self._device.orientation = orientation

    def press(self, key: Any) -> None:
        self._device.press(key)

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
        if steps is not None:
            self._device.swipe(fx, fy, tx, ty, steps=steps)
            return
        if duration is not None:
            self._device.swipe(fx, fy, tx, ty, duration=duration)
            return
        self._device.swipe(fx, fy, tx, ty)

    def click(self, x: float, y: float) -> None:
        self._device.click(x, y)

    def swipe_ext(self, direction: str, *, scale: float = 0.8) -> None:
        self._device.swipe_ext(direction, scale=scale)

    def double_click(self, x: float, y: float, *, duration: float = 0.1) -> None:
        self._device.double_click(x, y, duration=duration)

    def long_click(self, x: float, y: float, *, duration: float = 0.5) -> None:
        self._device.long_click(x, y, duration=duration)

    def send_keys(self, text: str, *, clear: bool = True) -> None:
        self._device.send_keys(text, clear=clear)

    def open_notification(self) -> None:
        self._device.open_notification()

    def open_quick_settings(self) -> None:
        self._device.open_quick_settings()

    def open_url(self, url: str) -> None:
        self._device.open_url(url)

    def app_start(self, package: str, **kwargs: Any) -> None:
        self._device.app_start(package, **kwargs)

    def app_stop(self, package: str) -> None:
        self._device.app_stop(package)

    def app_stop_all(self) -> None:
        self._device.app_stop_all()

    def app_clear(self, package: str) -> None:
        self._device.app_clear(package)

    def app_install(self, apk: str) -> None:
        self._device.app_install(apk)

    def app_uninstall(self, package: str) -> Any:
        return self._device.app_uninstall(package)

    def app_info(self, package: str) -> Any:
        return self._device.app_info(package)

    def app_list(self, pkg_filter: str = "") -> Any:
        return self._device.app_list(pkg_filter)

    def app_list_running(self) -> Any:
        return self._device.app_list_running()

    def app_wait(self, package: str, *, timeout: float = 20.0, front: bool = False) -> Any:
        return self._device.app_wait(package, timeout=timeout, front=front)
