from types import SimpleNamespace

from u2cli.backends.android_u2 import AndroidU2Backend


class FakeAndroidDevice:
    def __init__(self, media_session_output: str, *, current_package: str = "com.huawei.music") -> None:
        self.media_session_output = media_session_output
        self.current_package = current_package
        self.pressed = []

    def app_current(self):
        return {"package": self.current_package, "activity": "MainActivity"}

    def shell(self, command, timeout=60):
        assert command == "dumpsys media_session"
        return SimpleNamespace(output=self.media_session_output, exit_code=0)

    def press(self, key):
        self.pressed.append(key)


class FakeAndroidGestureElement:
    def __init__(self, device, selector):
        self.device = device
        self.selector = selector
        self.info = {
            "bounds": {
                "left": selector.get("left", 0),
                "top": selector.get("top", 0),
                "right": selector.get("right", 100),
                "bottom": selector.get("bottom", 100),
            }
        }

    def pinch_in(self, percent=100):
        self.device.pinch_calls.append(("in", self.selector, percent))

    def pinch_out(self, percent=100):
        self.device.pinch_calls.append(("out", self.selector, percent))

    def drag_to(self, *args, duration=0.5, **target_selector):
        if len(args) >= 2:
            self.device.element_drag_calls.append((self.selector, (args[0], args[1]), duration))
            return
        self.device.element_drag_calls.append((self.selector, target_selector, duration))


class FakeAndroidGestureDevice:
    def __init__(self):
        self.drag_calls = []
        self.select_calls = []
        self.pinch_calls = []
        self.element_drag_calls = []

    def __call__(self, **selector):
        if selector.get("text") == "Source":
            selector = {**selector, "left": 10, "top": 20, "right": 110, "bottom": 120}
        elif selector.get("text") == "Target":
            selector = {**selector, "left": 210, "top": 220, "right": 310, "bottom": 320}
        self.select_calls.append(selector)
        return FakeAndroidGestureElement(self, selector)

    def window_size(self):
        return (1000, 2000)

    def dump_hierarchy(self, **kwargs):
        return (
            "<hierarchy>"
            '<node class="android.widget.FrameLayout" bounds="[0,0][1000,2000]">'
            '<node class="android.widget.ImageView" text="Map" resource-id="com.demo:id/map" '
            'content-desc="Map canvas" bounds="[100,200][900,1800]" />'
            "</node>"
            "</hierarchy>"
        )

    def drag(self, sx, sy, ex, ey, duration=0.5):
        self.drag_calls.append((sx, sy, ex, ey, duration))


def test_android_backend_playback_info_parses_playing_track_for_current_package():
    backend = AndroidU2Backend(
        device=FakeAndroidDevice(
            media_session_output="""
Sessions Stack - have 2 sessions:
    com.android.mediacenter.mediasession com.huawei.music/com.android.mediacenter.mediasession (userId=0)
      package=com.huawei.music
      state=PlaybackState {state=3, position=787, buffered position=0, speed=1.0, updated=93664230, actions=311}
      metadata: size=35, description=落花流水, 陈奕迅, Life Continues
    other.session com.example.video/com.example.video.session (userId=0)
      package=com.example.video
      state=PlaybackState {state=2, position=1405, buffered position=0, speed=1.0, updated=93115863, actions=822}
      metadata: size=8, description=别的视频, 别的作者, 别的专辑
"""
        ),
        serial="ANDROID-1",
    )

    assert backend.playback_info() == {
        "source": "media_session",
        "requested_package": "com.huawei.music",
        "package": "com.huawei.music",
        "state": {
            "code": 3,
            "name": "playing",
            "position": 787,
            "buffered_position": 0,
            "speed": 1.0,
        },
        "track": {
            "title": "落花流水",
            "artist": "陈奕迅",
            "album": "Life Continues",
        },
    }


def test_android_backend_playback_info_returns_empty_track_when_package_has_no_session():
    backend = AndroidU2Backend(
        device=FakeAndroidDevice(
            media_session_output="""
Sessions Stack - have 1 sessions:
    other.session com.example.video/com.example.video.session (userId=0)
      package=com.example.video
      state=PlaybackState {state=2, position=1405, buffered position=0, speed=1.0, updated=93115863, actions=822}
      metadata: size=8, description=别的视频, 别的作者, 别的专辑
""",
            current_package="com.huawei.music",
        ),
        serial="ANDROID-1",
    )

    assert backend.playback_info() == {
        "source": "media_session",
        "requested_package": "com.huawei.music",
        "package": "com.huawei.music",
        "state": None,
        "track": None,
    }


def test_android_backend_media_control_maps_actions_to_media_keycodes():
    device = FakeAndroidDevice(media_session_output="")
    backend = AndroidU2Backend(device=device, serial="ANDROID-1")

    backend.media_control("play")
    backend.media_control("pause")
    backend.media_control("play-pause")
    backend.media_control("next")
    backend.media_control("previous")
    backend.media_control("stop")

    assert device.pressed == [126, 127, 85, 87, 88, 86]


def test_android_backend_drag_and_drop_uses_device_drag():
    device = FakeAndroidGestureDevice()
    backend = AndroidU2Backend(device=device, serial="ANDROID-1")

    backend.drag_and_drop(0.1, 0.2, 0.8, 0.9, duration=0.7)

    assert device.drag_calls == [(0.1, 0.2, 0.8, 0.9, 0.7)]


def test_android_backend_zoom_targets_smallest_node_covering_center_point():
    device = FakeAndroidGestureDevice()
    backend = AndroidU2Backend(device=device, serial="ANDROID-1")

    backend.zoom(0.5, 0.5, percent=40)

    assert device.select_calls == [
        {
            "resourceId": "com.demo:id/map",
            "text": "Map",
            "className": "android.widget.ImageView",
            "description": "Map canvas",
        }
    ]
    assert device.pinch_calls == [
        (
            "out",
            {
                "resourceId": "com.demo:id/map",
                "text": "Map",
                "className": "android.widget.ImageView",
                "description": "Map canvas",
            },
            40,
        )
    ]


def test_android_element_drag_to_uses_native_selector_drag_to():
    device = FakeAndroidGestureDevice()
    backend = AndroidU2Backend(device=device, serial="ANDROID-1")

    source = backend.select({"text": "Source"})
    target = backend.select({"text": "Target"})

    source.drag_to(target, duration=0.8)

    assert device.element_drag_calls == [
        ({"text": "Source", "left": 10, "top": 20, "right": 110, "bottom": 120}, (260, 270), 0.8)
    ]