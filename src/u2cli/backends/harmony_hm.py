"""Harmony backend skeleton backed by hmdriver2 + HDC."""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import time
import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from typing import Any, Optional

from u2cli.transports.hdc import run_hdc_shell


def _call_first(target: Any, method_names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    for method_name in method_names:
        method = getattr(target, method_name, None)
        if callable(method):
            try:
                return method(*args, **kwargs)
            except TypeError:
                return method(*args)
    raise NotImplementedError(f"Harmony backend skeleton does not expose any of: {', '.join(method_names)}")


def _read_first(target: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        attr = getattr(target, name, None)
        if attr is None:
            continue
        return attr() if callable(attr) else attr
    raise NotImplementedError(f"Harmony backend skeleton does not expose any of: {', '.join(names)}")


def _quote_xpath_literal(value: str) -> str:
    return repr(value)


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_BM_DUMP_ID_RE = re.compile(r"^ID:\s*\d+:\s*$")
_HARMONY_STATE_CODES = {
    "none": 0,
    "stopped": 1,
    "paused": 2,
    "playing": 3,
    "fast_forwarding": 4,
    "rewinding": 5,
    "buffering": 6,
    "error": 7,
    "connecting": 8,
}
_HARMONY_MEDIA_KEYCODE_MAP = {
    "play-pause": 10,
    "stop": 11,
    "next": 12,
    "previous": 13,
    "play": 2085,
    "pause": 2086,
}
_HARMONY_PRESS_KEY_ALIASES = {
    "recent": 2210,
    "recents": 2210,
    "recent_apps": 2210,
    "enter": 2054,
    "delete": 2055,
    "del": 2055,
    "menu": 2067,
    "volume_up": 16,
    "volume_down": 17,
    "power": 18,
}
_HARMONY_MEDIA_CONTROL_TIMEOUT = 15.0
_HARMONY_MEDIA_CONTROL_UNAVAILABLE_MARKERS = (
    "inaccessible or not found",
    "illegal argument",
    "usage: uitest",
    "unrecognized option",
    "device not founded or connected",
)
_HARMONY_DESKTOP_HIERARCHY_MARKERS = (
    "SCBDesktop_",
    "GridSwiper",
    "SwiperPage_Grid",
    "AppIconCommonView",
)


def _bounds_center(bounds: str) -> tuple[int, int]:
    match = _BOUNDS_RE.fullmatch(bounds)
    if not match:
        raise RuntimeError(f"invalid Harmony bounds: {bounds!r}")
    left, top, right, bottom = [int(group) for group in match.groups()]
    return ((left + right) // 2, (top + bottom) // 2)


def _walk_hierarchy(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        yield from _walk_hierarchy(child)


def _stringify_xml_attr(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _harmony_xml_attrs(attributes: dict[str, Any]) -> dict[str, str]:
    xml_attrs = {key: _stringify_xml_attr(value) for key, value in attributes.items() if value is not None}
    alias_map = {
        "type": "class",
        "description": "content-desc",
        "id": "resource-id",
        "bundleName": "package",
        "packageName": "package",
    }
    for source_name, alias_name in alias_map.items():
        if source_name in attributes and alias_name not in xml_attrs:
            xml_attrs[alias_name] = _stringify_xml_attr(attributes[source_name])
    return xml_attrs


def _harmony_hierarchy_dict_to_xml(node: dict[str, Any], *, is_root: bool = True) -> str:
    def build(current: dict[str, Any], *, root: bool = False) -> ET.Element:
        element = ET.Element("hierarchy" if root else "node", _harmony_xml_attrs(current.get("attributes", {})))
        for child in current.get("children", []):
            element.append(build(child))
        return element

    root = build(node, root=is_root)
    return ET.tostring(root, encoding="unicode")


def _extract_foreground_app_from_aa_dump(output: str) -> Optional[dict[str, str]]:
    if not output.strip():
        return None

    mission_starts = list(re.finditer(r"^\s*Mission ID #", output, re.MULTILINE))
    if not mission_starts:
        return None

    for index, match in enumerate(mission_starts):
        start = match.start()
        end = mission_starts[index + 1].start() if index + 1 < len(mission_starts) else len(output)
        block = output[start:end]
        if "state #FOREGROUND" not in block and "app state #FOREGROUND" not in block:
            continue

        bundle_match = re.search(r"bundle name \[(.*?)\]", block)
        main_match = re.search(r"main name \[(.*?)\]", block)
        package_name = bundle_match.group(1) if bundle_match else None
        activity_name = main_match.group(1) if main_match else None
        if package_name or activity_name:
            return {"package": package_name, "activity": activity_name}

    return None


def _truthy_hierarchy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _extract_current_app_from_hierarchy(hierarchy: Any) -> Optional[dict[str, str]]:
    if not isinstance(hierarchy, dict):
        return None

    for child in hierarchy.get("children", []):
        attributes = child.get("attributes", {})
        bundle_name = attributes.get("bundleName") or attributes.get("packageName")
        if not bundle_name:
            continue
        if not _truthy_hierarchy_flag(attributes.get("focused")):
            continue
        if attributes.get("visible") is not None and not _truthy_hierarchy_flag(attributes.get("visible")):
            continue

        activity_name = attributes.get("abilityName") or attributes.get("pagePath") or None
        return {"package": str(bundle_name), "activity": str(activity_name) if activity_name else None}

    return None


def _looks_like_harmony_desktop(hierarchy: Any) -> bool:
    if not isinstance(hierarchy, dict):
        return False

    for node in _walk_hierarchy(hierarchy):
        attributes = node.get("attributes", {})
        for value in attributes.values():
            if value is None:
                continue
            text = str(value)
            if any(marker in text for marker in _HARMONY_DESKTOP_HIERARCHY_MARKERS):
                return True
    return False


class HarmonyHmElement:
    """Thin wrapper around a hmdriver2 UI object."""

    def __init__(self, element: Any) -> None:
        self._element = element

    def click(self, *, timeout: float = 3.0) -> None:
        _wait_for_exists(self._element, timeout=timeout)
        _call_first(self._element, ("click",))

    def long_click(self, *, duration: float = 0.5, timeout: float = 3.0) -> None:
        _wait_for_exists(self._element, timeout=timeout)
        _call_first(self._element, ("long_click",), duration=duration)

    def get_text(self, *, timeout: float = 3.0) -> str:
        _wait_for_exists(self._element, timeout=timeout)
        return _read_first(self._element, ("get_text", "text"))

    def set_text(self, text: str, *, timeout: float = 3.0) -> None:
        _wait_for_exists(self._element, timeout=timeout)
        _call_first(self._element, ("input_text", "set_text"), text)

    def clear_text(self, *, timeout: float = 3.0) -> None:
        _wait_for_exists(self._element, timeout=timeout)
        _call_first(self._element, ("clear_text",))

    def exists(self, *, timeout: float = 0.0) -> bool:
        exists_fn = getattr(self._element, "exists", None)
        if callable(exists_fn):
            retries = max(1, math.ceil(timeout)) if timeout else 1
            try:
                return bool(exists_fn(retries=retries, wait_time=1))
            except TypeError:
                return bool(exists_fn())
        return bool(exists_fn)

    def wait(self, *, timeout: float = 3.0, gone: bool = False) -> bool:
        deadline = time.time() + timeout
        while time.time() <= deadline:
            current = self.exists(timeout=0.0)
            if gone and not current:
                return True
            if not gone and current:
                return True
            time.sleep(0.2)
        return False

    def info(self) -> Any:
        info_attr = getattr(self._element, "info", None)
        if info_attr is not None:
            return info_attr() if callable(info_attr) else info_attr
        component = getattr(self._element, "find_component", None)
        if callable(component):
            return component()
        raise NotImplementedError("Harmony backend skeleton does not expose element info yet")

    def swipe(self, direction: str, *, steps: int = 10) -> None:
        _call_first(self._element, ("swipe",), direction, steps=steps)

    def scroll(
        self,
        *,
        direction: str,
        action: str,
        max_swipes: int | None = None,
        to_text: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "Harmony backend skeleton does not expose scroll yet; add this when locator/scroll primitives are wired."
        )


class HarmonyHmLocator(HarmonyHmElement):
    """Locator wrapper for Harmony strategy-based element lookup."""


class HarmonyHierarchyLocator:
    """Locator backed by hierarchy inspection and coordinate actions."""

    def __init__(self, device: Any, predicate) -> None:
        self._device = device
        self._predicate = predicate

    def _resolve(self) -> Optional[dict[str, Any]]:
        hierarchy = _call_first(self._device, ("dump_hierarchy",))
        for node in _walk_hierarchy(hierarchy):
            attributes = node.get("attributes", {})
            if self._predicate(attributes):
                return attributes
        return None

    def exists(self) -> bool:
        return self._resolve() is not None

    def click(self, *, timeout: float = 3.0) -> None:
        if timeout > 0:
            deadline = time.time() + timeout
            while time.time() <= deadline:
                match = self._resolve()
                if match:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("element not found before timeout")
        else:
            match = self._resolve()
            if not match:
                raise RuntimeError("element not found before timeout")
        x, y = _bounds_center(match.get("bounds", ""))
        self._device.click(x, y)

    def get_text(self) -> str:
        match = self._resolve()
        if not match:
            raise RuntimeError("element not found")
        return str(match.get("text") or match.get("description") or match.get("id") or "")

    def set_text(self, text: str) -> None:
        self.click()
        _call_first(self._device, ("input_text",), text)


def _wait_for_exists(element: Any, *, timeout: float) -> None:
    if timeout <= 0:
        return
    element_wrapper = HarmonyHmElement(element)
    if not element_wrapper.wait(timeout=timeout):
        raise RuntimeError("element not found before timeout")


def _clear_focused_input(device: Any) -> bool:
    try:
        HarmonyHmElement(device(focused=True)).clear_text(timeout=0.0)
        return True
    except Exception:
        return False


def _parse_bm_dump_packages(output: str, *, pkg_filter: str = "") -> list[str]:
    packages: list[str] = []
    in_package_section = False

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if _BM_DUMP_ID_RE.match(stripped):
            in_package_section = True
            continue
        if not in_package_section:
            continue
        if raw_line[:1].strip():
            in_package_section = False
            continue
        package_name = stripped
        if pkg_filter and pkg_filter not in package_name:
            continue
        packages.append(package_name)

    return packages


def _extract_json_object(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        return json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _normalize_harmony_app_info(package: str, payload: dict[str, Any], *, installed: bool) -> dict[str, Any]:
    application_info = payload.get("applicationInfo") if isinstance(payload, dict) else {}
    if not isinstance(application_info, dict):
        application_info = {}

    abilities: list[str] = []
    for module in payload.get("hapModuleInfos", []) if isinstance(payload, dict) else []:
        if not isinstance(module, dict):
            continue
        for ability in module.get("abilityInfos", []):
            if not isinstance(ability, dict):
                continue
            name = ability.get("name")
            if name:
                abilities.append(str(name))

    return {
        "package": package,
        "installed": installed,
        "appIdentifier": payload.get("appIdentifier") if isinstance(payload, dict) else None,
        "name": application_info.get("name") or package,
        "label": application_info.get("label"),
        "vendor": application_info.get("vendor"),
        "versionName": application_info.get("versionName"),
        "versionCode": application_info.get("versionCode"),
        "systemApp": application_info.get("isSystemApp"),
        "enabled": application_info.get("enabled"),
        "removable": application_info.get("removable"),
        "distributionType": application_info.get("appDistributionType"),
        "entryModuleName": payload.get("entryModuleName") if isinstance(payload, dict) else None,
        "uid": application_info.get("uid"),
        "abilities": abilities,
    }


def _parse_harmony_avsession_session_info(output: str) -> dict[str, Any] | None:
    current_session_id = None
    session: dict[str, Any] = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Count") and line.endswith(": 0"):
            return None
        if line.startswith("current session id:"):
            current_session_id = line.split(":", 1)[1].strip()
            continue
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        if key == "is active":
            session["is_active"] = value.lower() == "true"
            continue
        if key == "is the topsession":
            session["is_top_session"] = value.lower() == "true"
            continue
        if key == "pid":
            session["pid"] = int(value)
            continue
        if key == "uid":
            session["uid"] = int(value)
            continue
        if key == "session type":
            session["session_type"] = value
            continue
        if key == "session tag":
            session["session_tag"] = value
            continue
        if key == "bundle name":
            session["package"] = value
            continue
        if key == "ability name":
            session["activity"] = value
            continue

    if not current_session_id:
        return None
    session["session_id"] = current_session_id
    return session


def _parse_harmony_avsession_controller_info(output: str, *, session_id: str | None) -> dict[str, Any] | None:
    blocks = output.split("curretn controller pid")
    selected: dict[str, Any] | None = None

    for block in blocks[1:]:
        state: dict[str, Any] = {}
        related_session_id = None
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(":"):
                state["controller_pid"] = int(line[1:].strip())
                continue
            if line.startswith("state"):
                state_name = line.split(":", 1)[1].strip().lower()
                state["code"] = _HARMONY_STATE_CODES.get(state_name)
                state["name"] = state_name
                continue
            if line.startswith("speed"):
                state["speed"] = float(line.split(":", 1)[1].strip())
                continue
            if line.startswith("elapsed time"):
                state["position"] = int(line.split(":", 1)[1].strip())
                continue
            if line.startswith("update time"):
                state["update_time"] = int(line.split(":", 1)[1].strip())
                continue
            if line.startswith("buffered time"):
                state["buffered_position"] = int(line.split(":", 1)[1].strip())
                continue
            if line.startswith("loopmode"):
                state["loop_mode"] = line.split(":", 1)[1].strip()
                continue
            if line.startswith("is favorite"):
                state["is_favorite"] = line.split(":", 1)[1].strip().lower() == "true"
                continue
            if line.startswith("Related Sessionid"):
                related_session_id = line.split(":", 1)[1].strip()

        if not state:
            continue
        state["session_id"] = related_session_id
        if session_id and related_session_id == session_id:
            return state
        if selected is None:
            selected = state

    return selected


def _parse_harmony_avsession_metadata(output: str) -> dict[str, Any] | None:
    wanted_keys = {
        "assetid": "asset_id",
        "title": "title",
        "artist": "artist",
        "album": "album",
        "duration": "duration",
        "subtitle": "subtitle",
        "description": "description",
        "media image url": "artwork_url",
    }
    in_metadata = False
    metadata: dict[str, Any] = {}

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "Metadata:":
            in_metadata = True
            continue
        if not in_metadata:
            continue
        if stripped.startswith("ControllerIndex:"):
            break
        if stripped.startswith("lyric"):
            continue
        if ":" not in stripped:
            continue
        key, value = [part.strip() for part in stripped.split(":", 1)]
        mapped_key = wanted_keys.get(key)
        if not mapped_key:
            continue
        metadata[mapped_key] = int(value) if mapped_key == "duration" and value.isdigit() else value

    return metadata or None
def _run_harmony_media_key_if_available(action: str, *, serial: str | None) -> str | None:
    keycode = _HARMONY_MEDIA_KEYCODE_MAP.get(action)
    if keycode is None:
        return None

    try:
        result = run_hdc_shell(
            ["uitest", "uiInput", "keyEvent", str(keycode)],
            serial=serial,
            timeout=_HARMONY_MEDIA_CONTROL_TIMEOUT,
        )
    except RuntimeError:
        return None
    message = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip()).strip()
    normalized = message.lower()

    if result.returncode == 0 and (not message or "no error" in normalized):
        return f"harmony_uitest_keyevent({keycode})"

    if any(marker in normalized for marker in _HARMONY_MEDIA_CONTROL_UNAVAILABLE_MARKERS):
        return None

    raise RuntimeError(f"Harmony zero-install media control failed: {message or f'hdc exit code {result.returncode}'}")


def run_harmony_media_control_if_available(action: str, *, serial: str | None) -> str | None:
    return _run_harmony_media_key_if_available(action, serial=serial)


def _swipe_ext_fallback(device: Any, direction: str, *, scale: float = 0.8) -> None:
    width, height = _read_first(device, ("display_size", "window_size"))
    horizontal_offset = int(width * (1 - scale) / 2)
    vertical_offset = int(height * (1 - scale) / 2)

    if direction == "left":
        start = (width - horizontal_offset, height // 2)
        end = (horizontal_offset, height // 2)
    elif direction == "right":
        start = (horizontal_offset, height // 2)
        end = (width - horizontal_offset, height // 2)
    elif direction == "up":
        start = (width // 2, height - vertical_offset)
        end = (width // 2, vertical_offset)
    elif direction == "down":
        start = (width // 2, vertical_offset)
        end = (width // 2, height - vertical_offset)
    else:
        raise ValueError(f"Unknown swipe direction: {direction}")

    _call_first(device, ("swipe",), start[0], start[1], end[0], end[1])


def _swipe_from_top_edge(device: Any, *, x_ratio: float, end_y_ratio: float = 0.72) -> None:
    width, height = _read_first(device, ("display_size", "window_size"))
    x = int(width * x_ratio)
    start_y = max(1, int(height * 0.02))
    end_y = int(height * end_y_ratio)
    _call_first(device, ("swipe",), x, start_y, x, end_y)


def _open_harmony_system_panel(device: Any, *, x_ratio: float) -> None:
    swipe_profiles = (0.72, 0.86)

    for index, end_y_ratio in enumerate(swipe_profiles):
        _swipe_from_top_edge(device, x_ratio=x_ratio, end_y_ratio=end_y_ratio)
        if index == len(swipe_profiles) - 1:
            return

        time.sleep(0.15)
        try:
            hierarchy = _call_first(device, ("dump_hierarchy",))
        except Exception:
            return

        if not _looks_like_harmony_desktop(hierarchy):
            return


class HarmonyHmBackend:
    """Thin stage-2 wrapper around a hmdriver2 driver instance."""

    platform = "harmony"
    backend_name = "hmdriver2+hdc"
    supported_locator_strategies = (
        "xpath",
        "id",
        "text",
        "text_contains",
        "text_regex",
        "text_startswith",
        "text_endswith",
    )
    supported_selector_fields = (
        "text",
        "textContains",
        "textMatches",
        "textStartsWith",
        "resourceId",
        "className",
        "description",
        "descriptionContains",
        "descriptionMatches",
        "descriptionStartsWith",
        "packageName",
        "index",
        "instance",
        "clickable",
        "scrollable",
        "enabled",
        "focused",
        "selected",
        "checked",
        "checkable",
    )

    def __init__(self, device: Any, serial: Optional[str] = None) -> None:
        self._device = device
        self.serial = serial

    def raw_device(self) -> Any:
        return self._device

    def _selector_uses_dynamic_resolution(self, selector: dict[str, Any]) -> bool:
        return any(
            key in selector
            for key in (
                "textContains",
                "textMatches",
                "textStartsWith",
                "descriptionContains",
                "descriptionMatches",
                "descriptionStartsWith",
                "packageName",
            )
        )

    def _attribute_value(self, attributes: dict[str, Any], *names: str) -> Any:
        for name in names:
            if name in attributes:
                return attributes.get(name)
        return None

    def _attribute_bool(self, attributes: dict[str, Any], *names: str) -> Optional[bool]:
        value = self._attribute_value(attributes, *names)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        return bool(value)

    def _selector_matches_attributes(self, selector: dict[str, Any], attributes: dict[str, Any]) -> bool:
        text = str(self._attribute_value(attributes, "text") or "")
        description = str(self._attribute_value(attributes, "description", "content-desc") or "")
        resource_id = str(self._attribute_value(attributes, "id", "resource-id") or "")
        class_name = str(self._attribute_value(attributes, "type", "class") or "")
        package_name = str(self._attribute_value(attributes, "packageName", "bundleName", "package") or "")

        if "text" in selector and text != selector["text"]:
            return False
        if "textContains" in selector and selector["textContains"] not in text:
            return False
        if "textMatches" in selector and not re.search(selector["textMatches"], text):
            return False
        if "textStartsWith" in selector and not text.startswith(selector["textStartsWith"]):
            return False
        if "resourceId" in selector and resource_id != selector["resourceId"]:
            return False
        if "className" in selector and class_name != selector["className"]:
            return False
        if "description" in selector and description != selector["description"]:
            return False
        if "descriptionContains" in selector and selector["descriptionContains"] not in description:
            return False
        if "descriptionMatches" in selector and not re.search(selector["descriptionMatches"], description):
            return False
        if "descriptionStartsWith" in selector and not description.startswith(selector["descriptionStartsWith"]):
            return False
        if "packageName" in selector and package_name != selector["packageName"]:
            return False

        bool_mapping = {
            "clickable": ("clickable",),
            "scrollable": ("scrollable",),
            "checkable": ("checkable",),
            "checked": ("checked",),
            "enabled": ("enabled",),
            "focused": ("focused",),
            "selected": ("selected",),
        }
        for selector_key, attribute_names in bool_mapping.items():
            if selector_key not in selector:
                continue
            attr_value = self._attribute_bool(attributes, *attribute_names)
            if attr_value is None or attr_value != selector[selector_key]:
                return False

        return True

    def _build_concrete_selector(self, selector: dict[str, Any], attributes: dict[str, Any]) -> dict[str, Any]:
        concrete: dict[str, Any] = {}
        dynamic_keys = {
            "textContains",
            "textMatches",
            "textStartsWith",
            "descriptionContains",
            "descriptionMatches",
            "descriptionStartsWith",
            "packageName",
        }

        passthrough_keys = (
            "resourceId",
            "className",
            "description",
            "index",
            "instance",
            "clickable",
            "scrollable",
            "checkable",
            "checked",
            "enabled",
            "focused",
            "selected",
        )
        for key in passthrough_keys:
            if key in selector:
                concrete[key] = selector[key]

        if "text" in selector:
            concrete["text"] = selector["text"]
        elif any(key in selector for key in dynamic_keys):
            matched_text = self._attribute_value(attributes, "text")
            if matched_text:
                concrete["text"] = matched_text

        if "description" not in concrete and "descriptionContains" in selector:
            matched_description = self._attribute_value(attributes, "description", "content-desc")
            if matched_description:
                concrete["description"] = matched_description
        elif "description" not in concrete and any(
            key in selector for key in ("descriptionMatches", "descriptionStartsWith")
        ):
            matched_description = self._attribute_value(attributes, "description", "content-desc")
            if matched_description:
                concrete["description"] = matched_description

        if "resourceId" not in concrete:
            matched_resource_id = self._attribute_value(attributes, "id", "resource-id")
            if matched_resource_id:
                concrete["resourceId"] = matched_resource_id

        if "className" not in concrete:
            matched_class_name = self._attribute_value(attributes, "type", "class")
            if matched_class_name:
                concrete["className"] = matched_class_name

        if not concrete:
            raise NotImplementedError("Harmony backend could not derive a concrete selector from the matched hierarchy node")
        return concrete

    def _resolve_dynamic_selector(self, selector: dict[str, Any]) -> dict[str, Any]:
        hierarchy = _call_first(self._device, ("dump_hierarchy",))
        matches = [
            node.get("attributes", {})
            for node in _walk_hierarchy(hierarchy)
            if self._selector_matches_attributes(selector, node.get("attributes", {}))
        ]

        instance = selector.get("instance")
        index = selector.get("index")
        target_index = instance if instance is not None else index if index is not None else 0
        if target_index >= len(matches):
            raise RuntimeError("element not found")

        return self._build_concrete_selector(selector, matches[target_index])

    def _map_selector(self, selector: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "text": "text",
            "resourceId": "id",
            "className": "type",
            "description": "description",
            "index": "index",
            "instance": "index",
            "clickable": "clickable",
            "scrollable": "scrollable",
            "checkable": "checkable",
            "checked": "checked",
            "enabled": "enabled",
            "focused": "focused",
            "selected": "selected",
        }
        unsupported = sorted(set(selector) - set(mapping))
        if unsupported:
            raise NotImplementedError(
                "Harmony backend skeleton does not yet support selector fields: " + ", ".join(unsupported)
            )
        return {mapping[key]: value for key, value in selector.items()}

    def select(self, selector: dict[str, Any]) -> HarmonyHmElement:
        resolved_selector = self._resolve_dynamic_selector(selector) if self._selector_uses_dynamic_resolution(selector) else selector
        return HarmonyHmElement(self._device(**self._map_selector(resolved_selector)))

    def _create_xpath_locator(self, expression: str) -> HarmonyHmLocator:
        xpath_fn = getattr(self._device, "xpath", None)
        if callable(xpath_fn):
            return HarmonyHmLocator(xpath_fn(expression))

        from hmdriver2._xpath import _XPath

        return HarmonyHmLocator(_XPath(self._device)(expression))

    def _create_regex_locator(self, pattern: str) -> HarmonyHierarchyLocator:
        regex = re.compile(pattern)

        def predicate(attributes: dict[str, Any]) -> bool:
            for key in ("text", "description", "id"):
                value = str(attributes.get(key, ""))
                if regex.search(value):
                    return True
            return False

        return HarmonyHierarchyLocator(self._device, predicate)

    def locate(self, strategy: str, value: str) -> HarmonyHmLocator:
        if strategy == "xpath":
            return self._create_xpath_locator(value)
        if strategy == "id":
            return HarmonyHmLocator(self._device(id=value))
        if strategy == "text":
            return HarmonyHmLocator(self._device(text=value))
        if strategy == "text_contains":
            quoted = _quote_xpath_literal(value)
            return self._create_xpath_locator(
                f"//*[contains(@text, {quoted}) or contains(@description, {quoted})]"
            )
        if strategy == "text_startswith":
            quoted = _quote_xpath_literal(value)
            return self._create_xpath_locator(
                f"//*[starts-with(@text, {quoted}) or starts-with(@description, {quoted})]"
            )
        if strategy == "text_endswith":
            quoted = _quote_xpath_literal(value)
            length = len(value)
            return self._create_xpath_locator(
                "//*[{value} = substring(@text, string-length(@text) - {length} + 1) or "
                "{value} = substring(@description, string-length(@description) - {length} + 1)]".format(
                    value=quoted,
                    length=length,
                )
            )
        if strategy == "text_regex":
            return self._create_regex_locator(value)
        raise NotImplementedError(
            f"Harmony backend skeleton does not yet support locator strategy: {strategy}"
        )

    def screenshot(self) -> Any:
        screenshot_fn = getattr(self._device, "screenshot", None)
        if callable(screenshot_fn):
            try:
                return screenshot_fn()
            except TypeError:
                from PIL import Image

                fd, temp_path = tempfile.mkstemp(prefix="u2cli-harmony-", suffix=".png")
                os.close(fd)
                cleanup_paths = [temp_path]
                try:
                    result = screenshot_fn(temp_path)
                    saved_path = result if isinstance(result, str) and os.path.exists(result) else temp_path
                    if saved_path not in cleanup_paths:
                        cleanup_paths.append(saved_path)
                    image = Image.open(saved_path)
                    image.load()
                    return image
                finally:
                    for cleanup_path in cleanup_paths:
                        if os.path.exists(cleanup_path):
                            os.unlink(cleanup_path)
        raise NotImplementedError("Harmony backend skeleton does not expose screenshot yet")

    def window_size(self) -> tuple[int, int]:
        size = _read_first(self._device, ("display_size", "window_size"))
        return int(size[0]), int(size[1])

    def shell(self, command: str, *, timeout: int = 60) -> Any:
        result = _call_first(self._device, ("shell",), command)
        if hasattr(result, "output") and hasattr(result, "exit_code"):
            return result
        return SimpleNamespace(output=str(result), exit_code=0)

    def current_app(self) -> Any:
        result = _call_first(self._device, ("current_app",))
        if isinstance(result, tuple) and len(result) >= 2:
            package_name, activity_name = result[0], result[1]
            if package_name or activity_name:
                return {"package": package_name, "activity": activity_name}
            empty_result = {"package": package_name, "activity": activity_name}
        else:
            empty_result = {"package": None, "activity": None}
        if isinstance(result, dict) and (result.get("package") or result.get("activity")):
            return result

        for command in ("aa dump -l", "aa dump --mission-list"):
            try:
                shell_result = self.shell(command)
            except Exception:
                continue
            fallback = _extract_foreground_app_from_aa_dump(str(getattr(shell_result, "output", "")))
            if fallback is not None:
                return fallback

        try:
            hierarchy = _call_first(self._device, ("dump_hierarchy",))
        except Exception:
            hierarchy = None
        hierarchy_fallback = _extract_current_app_from_hierarchy(hierarchy)
        if hierarchy_fallback is not None:
            return hierarchy_fallback

        return result if isinstance(result, dict) else empty_result

    def playback_info(self, *, package: str | None = None) -> Any:
        session_output = str(
            getattr(
                self.shell("hidumper -s AVSessionService -a '-show_session_info'"),
                "output",
                "",
            )
        )
        session = _parse_harmony_avsession_session_info(session_output)

        if session is None:
            return {
                "source": "avsession",
                "requested_package": package,
                "package": package,
                "activity": None,
                "state": None,
                "track": None,
            }

        active_package = session.get("package")
        if package and active_package != package:
            return {
                "source": "avsession",
                "requested_package": package,
                "package": package,
                "activity": None,
                "state": None,
                "track": None,
            }

        controller_output = str(
            getattr(
                self.shell("hidumper -s AVSessionService -a '-show_controller_info'"),
                "output",
                "",
            )
        )
        metadata_output = str(
            getattr(
                self.shell("hidumper -s AVSessionService -a '-show_metadata'"),
                "output",
                "",
            )
        )

        state = _parse_harmony_avsession_controller_info(controller_output, session_id=session.get("session_id"))
        track = _parse_harmony_avsession_metadata(metadata_output)

        return {
            "source": "avsession",
            "requested_package": package,
            "package": active_package,
            "activity": session.get("activity"),
            "state": state,
            "track": track,
        }

    def media_control(self, action: str) -> None:
        if run_harmony_media_control_if_available(action, serial=self.serial) is not None:
            return
        raise NotImplementedError(
            "Harmony backend could not use the built-in zero-install media-control path "
            "(uitest uiInput keyEvent)."
        )

    def device_info(self) -> Any:
        return {
            "platform": self.platform,
            "backend": self.backend_name,
            "serial": self.serial,
        }

    def ui_info(self) -> Any:
        width, height = self.window_size()
        return {"display": {"width": width, "height": height}, "platform": self.platform}

    def dump_hierarchy_xml(self, *, compressed: bool = False, max_depth: int | None = None) -> str:
        if hasattr(self._device, "dump_hierarchy"):
            hierarchy = _call_first(self._device, ("dump_hierarchy",), compressed=compressed, max_depth=max_depth)
            if isinstance(hierarchy, str):
                return hierarchy
            if isinstance(hierarchy, dict):
                return _harmony_hierarchy_dict_to_xml(hierarchy)
            raise NotImplementedError(
                f"Harmony backend skeleton returned unsupported hierarchy payload: {type(hierarchy).__name__}"
            )
        raise NotImplementedError("Harmony backend skeleton does not expose hierarchy dump yet")

    def screen_on(self) -> None:
        _call_first(self._device, ("unlock", "screen_on"))

    def screen_off(self) -> None:
        _call_first(self._device, ("sleep", "screen_off"))

    def get_orientation(self) -> Any:
        if hasattr(self._device, "orientation"):
            return self._device.orientation
        raise NotImplementedError("Harmony backend skeleton does not expose orientation yet")

    def set_orientation(self, orientation: str) -> None:
        raise NotImplementedError("Harmony backend skeleton does not support setting orientation yet")

    def press(self, key: Any) -> None:
        if isinstance(key, str):
            normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized == "home" and callable(getattr(self._device, "go_home", None)):
                self._device.go_home()
                return
            if normalized == "back" and callable(getattr(self._device, "go_back", None)):
                self._device.go_back()
                return
            alias_keycode = _HARMONY_PRESS_KEY_ALIASES.get(normalized)
            if alias_keycode is not None:
                key = alias_keycode
        _call_first(self._device, ("press_key", "press"), key)

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
        _call_first(self._device, ("swipe",), fx, fy, tx, ty)

    def click(self, x: float, y: float) -> None:
        _call_first(self._device, ("click",), x, y)

    def swipe_ext(self, direction: str, *, scale: float = 0.8) -> None:
        swipe_ext = getattr(self._device, "swipe_ext", None)
        if callable(swipe_ext):
            swipe_ext(direction, scale=scale)
            return
        _swipe_ext_fallback(self._device, direction, scale=scale)

    def double_click(self, x: float, y: float, *, duration: float = 0.1) -> None:
        _call_first(self._device, ("double_click",), x, y)

    def long_click(self, x: float, y: float, *, duration: float = 0.5) -> None:
        _call_first(self._device, ("long_click",), x, y, duration=duration)

    def send_keys(self, text: str, *, clear: bool = True) -> None:
        if clear:
            try:
                _call_first(self._device, ("clear_text",))
            except NotImplementedError:
                if not _clear_focused_input(self._device):
                    raise
        _call_first(self._device, ("input_text", "send_keys"), text)

    def open_notification(self) -> None:
        # Harmony commonly splits notification shade (left) and control center (right).
        _open_harmony_system_panel(self._device, x_ratio=0.2)

    def open_quick_settings(self) -> None:
        _swipe_from_top_edge(self._device, x_ratio=0.8)

    def open_url(self, url: str) -> None:
        open_url = getattr(self._device, "open_url", None)
        if callable(open_url):
            open_url(url)
            return
        self.shell(f"aa start -A ohos.want.action.viewData -e entity.system.browsable -U {url}")

    def app_start(self, package: str, **kwargs: Any) -> None:
        ability = kwargs.get("activity")
        _call_first(self._device, ("start_app",), package, ability)

    def app_stop(self, package: str) -> None:
        _call_first(self._device, ("stop_app",), package)

    def app_stop_all(self) -> None:
        raise NotImplementedError("Harmony backend skeleton does not support stopping all apps yet")

    def app_clear(self, package: str) -> None:
        _call_first(self._device, ("clear_app",), package)

    def app_install(self, apk: str) -> None:
        _call_first(self._device, ("install_app",), apk)

    def app_uninstall(self, package: str) -> Any:
        return _call_first(self._device, ("uninstall_app",), package)

    def app_info(self, package: str) -> Any:
        installed = bool(_call_first(self._device, ("has_app",), package))
        if not installed:
            return _normalize_harmony_app_info(package, {}, installed=False)

        payload = {}
        get_app_info = getattr(self._device, "get_app_info", None)
        if callable(get_app_info):
            payload = get_app_info(package) or {}
        if not payload:
            shell_result = self.shell(f"bm dump -n {package}")
            payload = _extract_json_object(str(getattr(shell_result, "output", "")))

        return _normalize_harmony_app_info(package, payload, installed=True)

    def app_list(self, pkg_filter: str = "") -> Any:
        shell_result = self.shell("bm dump -a")
        return _parse_bm_dump_packages(str(getattr(shell_result, "output", "")), pkg_filter=pkg_filter)

    def app_list_running(self) -> Any:
        current = self.current_app()
        package = current.get("package") if isinstance(current, dict) else None
        return [package] if package else []

    def app_wait(self, package: str, *, timeout: float = 20.0, front: bool = False) -> Any:
        deadline = time.time() + timeout
        while time.time() <= deadline:
            current = self.current_app()
            current_package = current.get("package") if isinstance(current, dict) else None
            if current_package == package:
                return package
            time.sleep(0.5)
        return None