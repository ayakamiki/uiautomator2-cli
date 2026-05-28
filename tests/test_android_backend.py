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