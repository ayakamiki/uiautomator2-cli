from types import SimpleNamespace
from unittest.mock import Mock, patch

from u2cli.backends.harmony_hm import HarmonyHmBackend
from u2cli.services.xpath import (
    HARMONY_REQUIRED_LOCATOR_STRATEGIES,
    HARMONY_LOCATOR_BOUNDARY,
    missing_required_locator_strategies,
)


class FakeHarmonyElement:
    def __init__(self, kwargs, driver):
        self.kwargs = kwargs
        self.driver = driver

    def click(self):
        self.driver.calls.append(("element_click", self.kwargs))

    def exists(self, retries=1, wait_time=1):
        return True

    @property
    def text(self):
        return self.kwargs.get("text") or self.kwargs.get("id") or ""

    def input_text(self, text):
        self.driver.calls.append(("element_input_text", self.kwargs, text))

    def clear_text(self):
        self.driver.calls.append(("element_clear_text", self.kwargs))


class FakeHarmonyDevice:
    def __init__(self):
        self.calls = []
        self.display_size = (1080, 2400)
        self.current_app_result = (None, None)
        self.shell_outputs = {}
        self.app_info_payloads = {}

    def __call__(self, **kwargs):
        self.calls.append(("select", kwargs))
        return FakeHarmonyElement(kwargs, self)

    def click(self, x, y):
        self.calls.append(("click", (x, y)))

    def swipe(self, x1, y1, x2, y2):
        self.calls.append(("swipe", (x1, y1, x2, y2)))

    def go_home(self):
        self.calls.append(("go_home",))

    def go_back(self):
        self.calls.append(("go_back",))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def input_text(self, text):
        self.calls.append(("input_text", text))

    def open_url(self, url):
        self.calls.append(("open_url", url))

    def dump_hierarchy(self):
        return {
            "attributes": {"type": "Root"},
            "children": [
                {
                    "attributes": {
                        "type": "Button",
                        "text": "Login Now",
                        "description": "Login button",
                        "id": "entry.login",
                        "bundleName": "com.demo.pkg",
                        "clickable": True,
                        "enabled": True,
                        "bounds": "[10,20][110,60]",
                    },
                    "children": [],
                }
            ],
        }

    def current_app(self):
        return self.current_app_result

    def shell(self, command):
        self.calls.append(("shell", command))
        return SimpleNamespace(output=self.shell_outputs.get(command, ""), exit_code=0)

    def has_app(self, package):
        return package in self.app_info_payloads or package in self.shell_outputs.get("bm dump -a", "")

    def get_app_info(self, package):
        self.calls.append(("get_app_info", package))
        return self.app_info_payloads.get(package, {})


class FakeHarmonyScreenshotDevice(FakeHarmonyDevice):
    def screenshot(self, path):
        from PIL import Image

        Image.new("RGB", (2, 3), color=(255, 0, 0)).save(path)
        return path


def test_harmony_backend_satisfies_required_locator_strategy_set():
    missing = missing_required_locator_strategies(
        HARMONY_LOCATOR_BOUNDARY,
        set(HarmonyHmBackend.supported_locator_strategies),
    )

    assert HarmonyHmBackend.supported_locator_strategies == HARMONY_REQUIRED_LOCATOR_STRATEGIES
    assert missing == set()


def test_harmony_backend_locate_supports_all_required_strategies():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.locate("id", "entry.login").exists() is True
    assert backend.locate("text", "Login Now").get_text() == "Login Now"
    assert backend.locate("text_contains", "Login").exists() is True
    assert backend.locate("text_startswith", "Log").exists() is True
    assert backend.locate("text_endswith", "Now").exists() is True
    assert backend.locate("text_regex", r"^Login.*").get_text() == "Login Now"
    assert backend.locate("xpath", "//Button[@text='Login Now']").exists() is True

    backend.locate("text_regex", r"^Login.*").click()
    backend.locate("text_contains", "Login").set_text("hello")

    assert ("select", {"id": "entry.login"}) in device.calls
    assert ("select", {"text": "Login Now"}) in device.calls
    assert ("click", (60, 40)) in device.calls
    assert ("input_text", "hello") in device.calls


def test_harmony_backend_select_maps_common_selector_fields():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.select(
        {
            "text": "Login",
            "resourceId": "entry.login",
            "className": "Button",
            "description": "Login button",
            "instance": 2,
            "clickable": True,
            "scrollable": False,
            "checkable": False,
            "checked": False,
            "enabled": True,
            "focused": False,
            "selected": False,
        }
    )

    assert device.calls[-1] == (
        "select",
        {
            "text": "Login",
            "id": "entry.login",
            "type": "Button",
            "description": "Login button",
            "index": 2,
            "clickable": True,
            "scrollable": False,
            "checkable": False,
            "checked": False,
            "enabled": True,
            "focused": False,
            "selected": False,
        },
    )


def test_harmony_backend_select_rejects_unmapped_selector_fields():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    try:
        backend.select({"packageName": "com.other.pkg", "textContains": "Login", "descriptionContains": "button"})
    except RuntimeError as exc:
        assert "element not found" in str(exc)
    else:
        raise AssertionError("Expected select() with unmatched dynamic selector to fail")


def test_harmony_backend_select_resolves_complex_selector_fields_to_native_selector():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    element = backend.select(
        {
            "textContains": "Login",
            "textMatches": r"Login.*",
            "textStartsWith": "Log",
            "descriptionContains": "button",
        }
    )

    assert element.get_text() == "Login Now"
    assert device.calls[-1] == (
        "select",
        {
            "text": "Login Now",
            "description": "Login button",
            "id": "entry.login",
            "type": "Button",
        },
    )


def test_harmony_backend_select_resolves_description_regex_and_startswith():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    element = backend.select(
        {
            "descriptionMatches": r"Login\s+button",
            "descriptionStartsWith": "Login",
        }
    )

    assert element.get_text() == "Login Now"
    assert device.calls[-1] == (
        "select",
        {
            "text": "Login Now",
            "description": "Login button",
            "id": "entry.login",
            "type": "Button",
        },
    )


def test_harmony_backend_select_uses_package_name_as_hierarchy_filter_only():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.select(
        {
            "packageName": "com.demo.pkg",
            "textContains": "Login",
        }
    )

    assert device.calls[-1] == (
        "select",
        {
            "text": "Login Now",
            "id": "entry.login",
            "type": "Button",
        },
    )


def test_harmony_backend_select_preserves_common_exact_filters_while_resolving_dynamic_fields():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.select(
        {
            "textContains": "Login",
            "className": "Button",
            "resourceId": "entry.login",
            "clickable": True,
        }
    )

    assert device.calls[-1] == (
        "select",
        {
            "text": "Login Now",
            "id": "entry.login",
            "type": "Button",
            "clickable": True,
        },
    )


def test_harmony_backend_select_still_rejects_unknown_selector_fields():
    backend = HarmonyHmBackend(device=Mock(), serial="HDC-1")

    try:
        backend.select({"textEndsWith": "Now"})
    except NotImplementedError as exc:
        assert "textEndsWith" in str(exc)
    else:
        raise AssertionError("Expected select() to reject unsupported selector fields")


def test_harmony_backend_window_size_reads_property_tuple():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    assert backend.window_size() == (1080, 2400)


def test_harmony_backend_dump_hierarchy_xml_serializes_driver_dict():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    xml_text = backend.dump_hierarchy_xml()

    assert "<hierarchy" in xml_text
    assert 'class="Button"' in xml_text
    assert 'content-desc="Login button"' in xml_text
    assert 'resource-id="entry.login"' in xml_text


def test_harmony_backend_screenshot_loads_image_from_path_based_driver_api():
    backend = HarmonyHmBackend(device=FakeHarmonyScreenshotDevice(), serial="HDC-1")

    image = backend.screenshot()

    assert image.size == (2, 3)


def test_harmony_backend_press_uses_home_and_back_navigation_methods_when_available():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.press("home")
    backend.press("back")
    backend.press(3)

    assert ("go_home",) in device.calls
    assert ("go_back",) in device.calls
    assert ("press_key", 3) in device.calls


def test_harmony_backend_press_maps_common_aliases_to_harmony_keycodes():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.press("recent")
    backend.press("enter")
    backend.press("delete")
    backend.press("menu")
    backend.press("volume_up")
    backend.press("volume-down")
    backend.press("power")

    assert device.calls == [
        ("press_key", 2210),
        ("press_key", 2054),
        ("press_key", 2055),
        ("press_key", 2067),
        ("press_key", 16),
        ("press_key", 17),
        ("press_key", 18),
    ]


def test_harmony_backend_send_keys_clears_focused_field_when_driver_lacks_clear_text():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.send_keys("hello", clear=True)

    assert ("select", {"focused": True}) in device.calls
    assert ("element_clear_text", {"focused": True}) in device.calls
    assert ("input_text", "hello") in device.calls


def test_harmony_backend_swipe_ext_falls_back_to_coordinate_swipe():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.swipe_ext("up", scale=0.5)

    assert ("swipe", (540, 1800, 540, 600)) in device.calls


def test_harmony_backend_open_notification_and_quick_settings_use_split_top_swipes():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.open_notification()
    backend.open_quick_settings()

    assert ("swipe", (216, 48, 216, 1728)) in device.calls
    assert ("swipe", (864, 48, 864, 1728)) in device.calls


def test_harmony_backend_open_notification_retries_with_stronger_swipe_when_hierarchy_still_looks_like_desktop():
    device = FakeHarmonyDevice()
    device.dump_hierarchy = Mock(
        side_effect=[
            {
                "attributes": {"id": "SCBDesktop_Flex_Desktop", "type": "Flex"},
                "children": [],
            }
        ]
    )
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    with patch("u2cli.backends.harmony_hm.time.sleep") as mock_sleep:
        backend.open_notification()

    assert ("swipe", (216, 48, 216, 1728)) in device.calls
    assert ("swipe", (216, 48, 216, 2064)) in device.calls
    mock_sleep.assert_called_once_with(0.15)


def test_harmony_backend_open_url_uses_driver_helper_when_available():
    device = FakeHarmonyDevice()
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    backend.open_url("https://example.com")

    assert ("open_url", "https://example.com") in device.calls


def test_harmony_backend_current_app_falls_back_to_aa_dump_foreground_parser():
    device = FakeHarmonyDevice()
    device.current_app_result = (None, None)
    device.shell_outputs["aa dump -l"] = """
User ID #100
    current mission lists:{
        Mission ID #34  mission name #[#com.huawei.hmos.settings:phone_settings:com.huawei.hmos.settings.MainAbility]
            AbilityRecord ID #4409
                app name [com.huawei.hmos.settings]
                main name [com.huawei.hmos.settings.MainAbility]
                bundle name [com.huawei.hmos.settings]
                ability type [PAGE]
                state #FOREGROUND  start time [25356428]
                app state #FOREGROUND
                ready #1  window attached #0  launcher #0
                isKeepAlive: false
    }
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.current_app() == {
        "package": "com.huawei.hmos.settings",
        "activity": "com.huawei.hmos.settings.MainAbility",
    }


def test_harmony_backend_current_app_keeps_none_when_no_foreground_mission_found():
    device = FakeHarmonyDevice()
    device.current_app_result = (None, None)
    device.shell_outputs["aa dump -l"] = "Mission ID #1\n  state #BACKGROUND\n"
    device.shell_outputs["aa dump --mission-list"] = "Mission ID #1\n  app state #BACKGROUND\n"
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.current_app() == {"package": None, "activity": None}


def test_harmony_backend_current_app_falls_back_to_focused_hierarchy_bundle_for_home_scene():
    device = FakeHarmonyDevice()
    device.current_app_result = (None, None)
    device.shell_outputs["aa dump -l"] = "Mission ID #1\n  state #BACKGROUND\n"
    device.shell_outputs["aa dump --mission-list"] = "Mission ID #1\n  app state #BACKGROUND\n"
    device.dump_hierarchy = lambda: {
        "attributes": {"type": "root"},
        "children": [
            {
                "attributes": {
                    "bundleName": "com.ohos.sceneboard",
                    "abilityName": "",
                    "pagePath": "",
                    "focused": "true",
                    "visible": "true",
                    "type": "WindowScene",
                },
                "children": [],
            },
            {
                "attributes": {
                    "bundleName": "com.huawei.hms.floatingnavigation",
                    "focused": "false",
                    "visible": "true",
                },
                "children": [],
            },
        ],
    }
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.current_app() == {"package": "com.ohos.sceneboard", "activity": None}


def test_harmony_backend_playback_info_reads_active_avsession_metadata_and_state():
    device = FakeHarmonyDevice()
    device.shell_outputs["hidumper -s AVSessionService -a '-show_session_info'"] = """
Session Information:

Count                        : 1

current session id: SESSION-001
State:
is active                    : true
is the topsession            : true

Configuration:
pid                          : 10527
uid                          : 20020048
session type                 : audio
session tag                  : AVSessionPlayer
bundle name                  : com.huawei.hmsapp.music
ability name                 : MainAbility
"""
    device.shell_outputs["hidumper -s AVSessionService -a '-show_controller_info'"] = """
Controller Information:

Count                        : 2

curretn controller pid       : 3097
State:
state                        : playing
speed                        : 1.000000
position
        elapsed time                 : 1305
        update time                  : 1779947299714
buffered time                : 0
loopmode                     : list
is favorite                  : false

Related Sessionid            : SESSION-001
"""
    device.shell_outputs["hidumper -s AVSessionService -a '-show_metadata'"] = """
ControllerIndex: 1
ItemIndex: 1
Metadata:
        assetid              : 74691735
        title                : 我知道你很难过
        artist               : cici_
        album                : 我知道你很难过
        duration             : 200907
        subtitle             : cici_ - 我知道你很难过
        description          : 我知道你很难过;cici_
        media image url      : https://example.com/cover.jpg
        lyric                : [00:00.00]...
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.playback_info() == {
        "source": "avsession",
        "requested_package": None,
        "package": "com.huawei.hmsapp.music",
        "activity": "MainAbility",
        "state": {
            "controller_pid": 3097,
            "code": 3,
            "name": "playing",
            "speed": 1.0,
            "position": 1305,
            "update_time": 1779947299714,
            "buffered_position": 0,
            "loop_mode": "list",
            "is_favorite": False,
            "session_id": "SESSION-001",
        },
        "track": {
            "asset_id": "74691735",
            "title": "我知道你很难过",
            "artist": "cici_",
            "album": "我知道你很难过",
            "duration": 200907,
            "subtitle": "cici_ - 我知道你很难过",
            "description": "我知道你很难过;cici_",
            "artwork_url": "https://example.com/cover.jpg",
        },
    }


def test_harmony_backend_playback_info_respects_package_filter_and_handles_empty_session():
    device = FakeHarmonyDevice()
    device.shell_outputs["hidumper -s AVSessionService -a '-show_session_info'"] = """
Session Information:

Count                        : 0
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.playback_info(package="com.tencent.hm.qqmusic") == {
        "source": "avsession",
        "requested_package": "com.tencent.hm.qqmusic",
        "package": "com.tencent.hm.qqmusic",
        "activity": None,
        "state": None,
        "track": None,
    }


def test_harmony_backend_playback_info_returns_empty_when_active_session_package_differs():
    device = FakeHarmonyDevice()
    device.shell_outputs["hidumper -s AVSessionService -a '-show_session_info'"] = """
Session Information:

Count                        : 1

current session id: SESSION-001
State:
is active                    : true
is the topsession            : true

Configuration:
bundle name                  : com.huawei.hmsapp.music
ability name                 : MainAbility
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.playback_info(package="com.tencent.hm.qqmusic") == {
        "source": "avsession",
        "requested_package": "com.tencent.hm.qqmusic",
        "package": "com.tencent.hm.qqmusic",
        "activity": None,
        "state": None,
        "track": None,
    }


def test_harmony_backend_media_control_uses_zero_install_uitest_keyevent_when_available():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    with patch("u2cli.backends.harmony_hm.run_hdc_shell") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="No Error", stderr="")
        backend.media_control("play-pause")

    mock_run.assert_called_once_with(
        ["uitest", "uiInput", "keyEvent", "10"],
        serial="HDC-1",
        timeout=15.0,
    )


def test_harmony_backend_media_control_stop_dispatches_zero_install_keyevent_without_assuming_state():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    # Real-device validation showed that keycode 11 reaches the player, but tested
    # Harmony music apps interpret it as a pause-style transition instead of a
    # strict stopped state. Keep the automated check at the dispatch boundary.
    with patch("u2cli.backends.harmony_hm.run_hdc_shell") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="No Error", stderr="")
        backend.media_control("stop")

    mock_run.assert_called_once_with(
        ["uitest", "uiInput", "keyEvent", "11"],
        serial="HDC-1",
        timeout=15.0,
    )


def test_harmony_backend_media_control_without_zero_install_path_keeps_blocker_message():
    backend = HarmonyHmBackend(device=FakeHarmonyDevice(), serial="HDC-1")

    with patch("u2cli.backends.harmony_hm.run_hdc_shell") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="Illegal argument: keyEvent", stderr="")
        try:
            backend.media_control("play")
        except NotImplementedError as exc:
            assert "zero-install media-control path" in str(exc)
        else:
            raise AssertionError("Expected unavailable zero-install path to keep explicit blocker")


def test_harmony_backend_app_list_parses_bm_dump_output_and_applies_filter():
    device = FakeHarmonyDevice()
    device.shell_outputs["bm dump -a"] = """
ID: 100:
        com.tencent.hm.qqmusic
        com.huawei.hmos.settings
        com.amap.hmapp
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.app_list() == [
        "com.tencent.hm.qqmusic",
        "com.huawei.hmos.settings",
        "com.amap.hmapp",
    ]
    assert backend.app_list("qqmusic") == ["com.tencent.hm.qqmusic"]


def test_harmony_backend_app_info_uses_driver_metadata_when_available():
    device = FakeHarmonyDevice()
    device.app_info_payloads["com.tencent.hm.qqmusic"] = {
        "appIdentifier": "5765880207853000627",
        "entryModuleName": "entry",
        "applicationInfo": {
            "name": "com.tencent.hm.qqmusic",
            "label": "$string:app_name",
            "vendor": "tme",
            "versionName": "2.10.0.5",
            "versionCode": 2100005,
            "isSystemApp": False,
            "enabled": True,
            "removable": True,
            "appDistributionType": "app_gallery",
            "uid": 20020284,
        },
        "hapModuleInfos": [
            {
                "abilityInfos": [
                    {"name": "EntryAbility"},
                    {"name": "PlayerAbility"},
                ]
            }
        ],
    }
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.app_info("com.tencent.hm.qqmusic") == {
        "package": "com.tencent.hm.qqmusic",
        "installed": True,
        "appIdentifier": "5765880207853000627",
        "name": "com.tencent.hm.qqmusic",
        "label": "$string:app_name",
        "vendor": "tme",
        "versionName": "2.10.0.5",
        "versionCode": 2100005,
        "systemApp": False,
        "enabled": True,
        "removable": True,
        "distributionType": "app_gallery",
        "entryModuleName": "entry",
        "uid": 20020284,
        "abilities": ["EntryAbility", "PlayerAbility"],
    }


def test_harmony_backend_app_info_falls_back_to_shell_json_and_marks_missing_packages():
    device = FakeHarmonyDevice()
    device.shell_outputs["bm dump -a"] = "com.huawei.hmos.settings\n"
    device.shell_outputs["bm dump -n com.huawei.hmos.settings"] = """
com.huawei.hmos.settings:
{
  "entryModuleName": "phone_settings",
  "applicationInfo": {
    "name": "com.huawei.hmos.settings",
    "versionName": "6.1.1.343",
    "versionCode": 601001343,
    "isSystemApp": true,
    "enabled": true,
    "removable": false,
    "appDistributionType": "os_integration",
    "uid": 20020046
  },
  "hapModuleInfos": [
    {"abilityInfos": [{"name": "MainAbility"}]}
  ]
}
"""
    backend = HarmonyHmBackend(device=device, serial="HDC-1")

    assert backend.app_info("com.huawei.hmos.settings") == {
        "package": "com.huawei.hmos.settings",
        "installed": True,
        "appIdentifier": None,
        "name": "com.huawei.hmos.settings",
        "label": None,
        "vendor": None,
        "versionName": "6.1.1.343",
        "versionCode": 601001343,
        "systemApp": True,
        "enabled": True,
        "removable": False,
        "distributionType": "os_integration",
        "entryModuleName": "phone_settings",
        "uid": 20020046,
        "abilities": ["MainAbility"],
    }

    assert backend.app_info("com.example.missing") == {
        "package": "com.example.missing",
        "installed": False,
        "appIdentifier": None,
        "name": "com.example.missing",
        "label": None,
        "vendor": None,
        "versionName": None,
        "versionCode": None,
        "systemApp": None,
        "enabled": None,
        "removable": None,
        "distributionType": None,
        "entryModuleName": None,
        "uid": None,
        "abilities": [],
    }