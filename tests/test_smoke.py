from click.testing import CliRunner

from u2cli.smoke import smoke_cli


class FakeImage:
    def __init__(self) -> None:
        self.size = (1080, 2400)
        self.saved_to = None

    def save(self, path: str) -> None:
        self.saved_to = path


class FakeBackend:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.playback_info_called = False
        self.image = FakeImage()

    def device_info(self):
        return {"platform": self.platform}

    def window_size(self):
        return (1080, 2400)

    def current_app(self):
        return {"package": "com.demo.app", "activity": "MainActivity"}

    def screenshot(self):
        return self.image

    def dump_hierarchy_xml(self):
        return "<hierarchy><node /></hierarchy>"

    def playback_info(self):
        self.playback_info_called = True
        return {"source": "media_session", "track": {"title": "demo"}}


def test_smoke_cli_runs_android_steps_and_includes_playback_info(monkeypatch):
    runner = CliRunner()
    backend = FakeBackend(platform="android")

    monkeypatch.setattr("u2cli.smoke.connect_backend", lambda serial, platform: backend)

    result = runner.invoke(smoke_cli, ["--platform", "android", "--json"])

    assert result.exit_code == 0
    assert '"ok": true' in result.output
    assert '"name": "playback_info"' in result.output
    assert backend.playback_info_called is True


def test_smoke_cli_runs_harmony_steps_and_includes_playback_info(monkeypatch):
    runner = CliRunner()
    backend = FakeBackend(platform="harmony")

    monkeypatch.setattr("u2cli.smoke.connect_backend", lambda serial, platform: backend)

    result = runner.invoke(smoke_cli, ["--platform", "harmony", "--json"])

    assert result.exit_code == 0
    assert '"name": "playback_info"' in result.output
    assert backend.playback_info_called is True