from types import SimpleNamespace
from unittest.mock import Mock, patch

from click.testing import CliRunner

from u2cli.app import (
    cmd_app_clear,
    cmd_app_info,
    cmd_app_install,
    cmd_app_list,
    cmd_app_list_running,
    cmd_app_start,
    cmd_app_stop,
    cmd_app_uninstall,
    cmd_app_wait,
)
from u2cli.cli import cli
from u2cli.element import (
    cmd_clear_text,
    cmd_click,
    cmd_element_info,
    cmd_exists,
    cmd_get_text,
    cmd_long_click,
    cmd_scroll,
    cmd_set_text,
    cmd_swipe_element,
    cmd_wait,
    cmd_xpath_click,
    cmd_xpath_exists,
    cmd_xpath_get_text,
    cmd_xpath_set_text,
)
from u2cli.screen import (
    cmd_click_coord,
    cmd_current_app,
    cmd_device_info,
    cmd_dump_hierarchy,
    cmd_double_click,
    cmd_long_click_coord,
    cmd_media_control,
    cmd_open_notification,
    cmd_open_quick_settings,
    cmd_open_url,
    cmd_orientation,
    cmd_playback_info,
    cmd_press,
    cmd_screen_off,
    cmd_screen_on,
    cmd_screenshot,
    cmd_send_keys,
    cmd_shell,
    cmd_swipe,
    cmd_swipe_ext,
    cmd_ui_info,
    cmd_window_size,
)
from u2cli.services.hierarchy import create_hierarchy_service
from u2cli.services.xpath import (
    HARMONY_REQUIRED_LOCATOR_STRATEGIES,
    create_xpath_service,
    missing_required_locator_strategies,
    parse_xpath_expression,
    resolve_xpath_for_platform,
)


class FakeImage:
    def __init__(self, size=(100, 200)):
        self.size = size
        self.saved_to = None

    def save(self, path):
        self.saved_to = path


def test_element_commands_use_backend_api():
    runner = CliRunner()
    element = Mock()
    element.get_text.return_value = "hello"
    element.exists.return_value = True
    element.wait.return_value = True
    element.info.return_value = {"text": "Login"}
    backend = Mock()
    backend.select.return_value = element

    with patch("u2cli.element.connect_backend", return_value=backend), patch("u2cli.element.output_result") as mock_output:
        result_click = runner.invoke(cmd_click, ["--text", "Login"])
        result_long_click = runner.invoke(cmd_long_click, ["--text", "Login"])
        result_get_text = runner.invoke(cmd_get_text, ["--text", "Login"])
        result_set_text = runner.invoke(cmd_set_text, ["--resource-id", "login_field", "hello"])
        result_clear_text = runner.invoke(cmd_clear_text, ["--text", "Login"])
        result_exists = runner.invoke(cmd_exists, ["--text", "Login"])
        result_wait = runner.invoke(cmd_wait, ["--text", "Login"])
        result_info = runner.invoke(cmd_element_info, ["--text", "Login"])
        result_swipe_element = runner.invoke(cmd_swipe_element, ["--text", "Login", "--direction", "left"])
        result_scroll = runner.invoke(cmd_scroll, ["--text", "Login", "--to-text", "More"])

    assert result_click.exit_code == 0
    assert result_long_click.exit_code == 0
    assert result_get_text.exit_code == 0
    assert result_set_text.exit_code == 0
    assert result_clear_text.exit_code == 0
    assert result_exists.exit_code == 0
    assert result_wait.exit_code == 0
    assert result_info.exit_code == 0
    assert result_swipe_element.exit_code == 0
    assert result_scroll.exit_code == 0
    backend.select.assert_any_call({"text": "Login"})
    element.click.assert_called_once_with(timeout=3.0)
    element.long_click.assert_called_once_with(duration=0.5, timeout=3.0)
    element.get_text.assert_called_once_with(timeout=3.0)
    element.set_text.assert_called_once_with("hello", timeout=3.0)
    element.clear_text.assert_called_once_with(timeout=3.0)
    element.exists.assert_called_once_with(timeout=0.0)
    element.wait.assert_called_once_with(timeout=3.0, gone=False)
    element.info.assert_called_once_with()
    element.swipe.assert_called_once_with("left", steps=10)
    element.scroll.assert_called_once_with(direction="vert", action="forward", to_text="More")
    assert mock_output.call_count == 10


def test_element_selector_cli_exposes_description_pattern_options():
    runner = CliRunner()
    element = Mock()
    backend = Mock()
    backend.select.return_value = element

    with patch("u2cli.element.connect_backend", return_value=backend), patch("u2cli.element.output_result"):
        result = runner.invoke(
            cmd_click,
            [
                "--description-matches",
                "Login.*button",
                "--description-starts-with",
                "Login",
            ],
        )

    assert result.exit_code == 0
    backend.select.assert_called_once_with(
        {
            "descriptionMatches": "Login.*button",
            "descriptionStartsWith": "Login",
        }
    )
    element.click.assert_called_once_with(timeout=3.0)


def test_top_level_help_explains_platform_default_and_harmony_opt_in():
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])
    normalized_output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "--platform [android|harmony|auto]" in result.output
    assert "--no-daemon" in result.output
    assert "[default: auto]" in result.output
    assert "auto resolves to android; harmony requires explicit opt-in" in normalized_output


def test_daemon_help_uses_platform_serial_terminology():
    runner = CliRunner()

    result = runner.invoke(cli, ["daemon", "--help"])
    normalized_output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Manage the background u2cli daemon for the current platform/serial target." in normalized_output
    assert "Show daemon log tail for the current platform/serial target." in normalized_output
    assert "Restart daemon for the current platform/serial target." in normalized_output
    assert "Start daemon for the current platform/serial target." in normalized_output
    assert "Show daemon status for the current platform/serial target." in normalized_output
    assert "Stop daemon for the current platform/serial target." in normalized_output


def test_no_daemon_flag_bypasses_background_delegation():
    runner = CliRunner()
    element = Mock()
    backend = Mock()
    backend.select.return_value = element

    with patch("u2cli.cli.run_via_daemon") as mock_run_via_daemon, patch(
        "u2cli.element.connect_backend",
        return_value=backend,
    ), patch("u2cli.element.output_result"):
        result = runner.invoke(cli, ["--no-daemon", "click", "--text", "Login"])

    assert result.exit_code == 0
    mock_run_via_daemon.assert_not_called()
    backend.select.assert_called_once_with({"text": "Login"})
    element.click.assert_called_once_with(timeout=3.0)


def test_daemon_restart_command_uses_restart_helper():
    runner = CliRunner()

    with patch("u2cli.cli.restart_daemon", return_value=(True, "u2cli daemon started")) as mock_restart:
        result = runner.invoke(cli, ["--platform", "harmony", "daemon", "restart", "--full-output-log"])

    assert result.exit_code == 0
    mock_restart.assert_called_once_with(None, platform="harmony", full_output_log=True)


def test_daemon_status_prints_code_fingerprint_when_available():
    runner = CliRunner()

    with patch(
        "u2cli.cli.daemon_status",
        return_value={
            "running": True,
            "socket": "/tmp/a.sock",
            "pid_file": "/tmp/a.pid",
            "log_file": "/tmp/a.log",
            "full_output_log": False,
            "code_fingerprint": "fresh123",
            "started_at": 100,
            "last_request_at": 120,
            "request_count": 3,
            "backend_cached": True,
            "active_device_id": "SERIAL-A",
            "pid": 4321,
        },
    ):
        result = runner.invoke(cli, ["daemon", "status"])

    assert result.exit_code == 0
    assert "code_fingerprint: fresh123" in result.output
    assert "started_at: 100" in result.output
    assert "last_request_at: 120" in result.output
    assert "request_count: 3" in result.output
    assert "backend_cached: True" in result.output
    assert "active_device_id: SERIAL-A" in result.output


def test_daemon_logs_reads_platform_specific_log_tail():
    runner = CliRunner()

    with patch("u2cli.cli.read_log_tail", return_value="") as mock_read:
        result = runner.invoke(cli, ["--platform", "harmony", "daemon", "logs", "--lines", "5"])

    assert result.exit_code == 0
    mock_read.assert_called_once_with(None, lines=5, platform="harmony")


def test_cross_platform_help_avoids_android_specific_app_and_ui_terms():
    runner = CliRunner()

    app_start_help = runner.invoke(cmd_app_start, ["--help"])
    app_clear_help = runner.invoke(cmd_app_clear, ["--help"])
    app_info_help = runner.invoke(cmd_app_info, ["--help"])
    app_install_help = runner.invoke(cmd_app_install, ["--help"])
    app_uninstall_help = runner.invoke(cmd_app_uninstall, ["--help"])
    ui_info_help = runner.invoke(cmd_ui_info, ["--help"])
    open_url_help = runner.invoke(cmd_open_url, ["--help"])
    current_app_help = runner.invoke(cmd_current_app, ["--help"])
    playback_info_help = runner.invoke(cmd_playback_info, ["--help"])
    press_help = runner.invoke(cmd_press, ["--help"])

    assert app_start_help.exit_code == 0
    assert app_clear_help.exit_code == 0
    assert app_info_help.exit_code == 0
    assert app_install_help.exit_code == 0
    assert app_uninstall_help.exit_code == 0
    assert ui_info_help.exit_code == 0
    assert open_url_help.exit_code == 0
    assert current_app_help.exit_code == 0
    assert playback_info_help.exit_code == 0
    assert press_help.exit_code == 0

    app_start_normalized = " ".join(app_start_help.output.split())
    app_clear_normalized = " ".join(app_clear_help.output.split())
    app_info_normalized = " ".join(app_info_help.output.split())
    app_install_normalized = " ".join(app_install_help.output.split())
    app_uninstall_normalized = " ".join(app_uninstall_help.output.split())
    ui_info_normalized = " ".join(ui_info_help.output.split())
    open_url_normalized = " ".join(open_url_help.output.split())
    current_app_normalized = " ".join(current_app_help.output.split())
    playback_info_normalized = " ".join(playback_info_help.output.split())
    press_normalized = " ".join(press_help.output.split())

    assert "Start (launch) an app by package/bundle identifier." in app_start_normalized
    assert "Clear app data for a package/bundle identifier." in app_clear_normalized
    assert "Get app metadata such as version and installation state." in app_info_normalized
    assert "Install an app package from a local path or URL." in app_install_normalized
    assert "Uninstall an app by package/bundle identifier." in app_uninstall_normalized
    assert "Show UI runtime info (screen size, orientation, current app, platform)." in ui_info_normalized
    assert "Open a URL in the default browser or system handler." in open_url_normalized
    assert (
        "Show the current foreground app info (package/bundle and activity/ability when available)."
        in current_app_normalized
    )
    assert (
        "Show media playback info using `dumpsys media_session` on Android or `AVSessionService` hidumper on Harmony."
        in playback_info_normalized
    )
    assert "Common named keys: home, back, menu, enter, delete, recent, volume_up, volume_down, power." in press_normalized
    assert "Harmony real-device validated aliases: home, back, recent, menu, enter, delete, volume_up, volume_down, power." in press_normalized
    assert "enter/delete were also verified end to end inside a real note-editor input field." in press_normalized
    assert "activity/ability to launch when supported" in app_start_normalized
    assert "versionName" not in app_info_normalized
    assert "versionCode" not in app_info_normalized
    assert "UiAutomator device info" not in ui_info_normalized
    assert "via intent" not in open_url_normalized


def test_playback_info_command_uses_backend_api():
    runner = CliRunner()
    backend = Mock()
    backend.platform = "android"
    backend.playback_info.return_value = {
        "source": "media_session",
        "package": "com.huawei.music",
        "state": {"code": 3, "name": "playing"},
        "track": {"title": "落花流水", "artist": "陈奕迅", "album": "Life Continues"},
    }

    with patch("u2cli.screen.connect_backend", return_value=backend), patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cmd_playback_info, ["--package", "com.huawei.music"])

    assert result.exit_code == 0
    backend.playback_info.assert_called_once_with(package="com.huawei.music")
    mock_output.assert_called_once_with(backend.playback_info.return_value, "d.shell('dumpsys media_session')")


def test_playback_info_command_uses_harmony_avsession_u2_code():
    runner = CliRunner()
    backend = Mock()
    backend.platform = "harmony"
    backend.playback_info.return_value = {
        "source": "avsession",
        "package": "com.huawei.hmsapp.music",
        "state": {"code": 2, "name": "paused"},
        "track": {"title": "七里香", "artist": "周杰伦", "album": "七里香"},
    }

    with patch("u2cli.screen.connect_backend", return_value=backend), patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cmd_playback_info, [])

    assert result.exit_code == 0
    backend.playback_info.assert_called_once_with(package=None)
    mock_output.assert_called_once_with(
        backend.playback_info.return_value,
        "d.shell(\"hidumper -s AVSessionService -a '-show_session_info'\")",
    )


def test_media_control_command_uses_backend_api():
    runner = CliRunner()
    backend = Mock()

    with patch("u2cli.screen.run_harmony_media_control_if_available", return_value=None), patch(
        "u2cli.screen.connect_backend",
        return_value=backend,
    ), patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cmd_media_control, ["next"])

    assert result.exit_code == 0
    backend.media_control.assert_called_once_with("next")
    mock_output.assert_called_once()


def test_media_control_command_surfaces_backend_blocker_as_click_error():
    runner = CliRunner()
    backend = Mock()
    backend.media_control.side_effect = NotImplementedError("not supported")

    with patch("u2cli.screen.run_harmony_media_control_if_available", return_value=None), patch(
        "u2cli.screen.connect_backend",
        return_value=backend,
    ):
        result = runner.invoke(cmd_media_control, ["play"])

    assert result.exit_code != 0
    assert "not supported" in result.output


def test_media_control_command_uses_harmony_fast_path_before_backend_connect():
    runner = CliRunner()

    with patch("u2cli.screen.run_harmony_media_control_if_available", return_value="harmony_uitest_keyevent(10)") as mock_harmony, patch(
        "u2cli.screen.connect_backend"
    ) as mock_connect_backend, patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cmd_media_control, ["--help"])

    assert result.exit_code == 0
    assert "pause-like transition" in result.output
    mock_harmony.assert_not_called()
    mock_connect_backend.assert_not_called()
    mock_output.assert_not_called()


def test_media_control_command_harmony_fast_path_bypasses_backend_connect():
    runner = CliRunner()

    with patch(
        "u2cli.screen.run_harmony_media_control_if_available",
        return_value="harmony_uitest_keyevent(2085)",
    ) as mock_harmony, patch(
        "u2cli.screen.connect_backend"
    ) as mock_connect_backend, patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cli, ["--no-daemon", "--platform", "harmony", "-s", "HDC-1", "media-control", "play"])

    assert result.exit_code == 0
    mock_harmony.assert_called_once_with("play", serial="HDC-1")
    mock_connect_backend.assert_not_called()
    mock_output.assert_called_once()


def test_media_control_command_harmony_fast_path_surfaces_unavailable_error_without_backend_connect():
    runner = CliRunner()

    with patch("u2cli.screen.run_harmony_media_control_if_available", return_value=None), patch(
        "u2cli.screen.connect_backend"
    ) as mock_connect_backend:
        result = runner.invoke(cli, ["--no-daemon", "--platform", "harmony", "-s", "HDC-1", "media-control", "play"])

    assert result.exit_code != 0
    assert "zero-install" in result.output
    mock_connect_backend.assert_not_called()


def test_xpath_service_uses_normalized_hierarchy_queries():
    element_handle = Mock()
    backend = Mock()
    backend.platform = "android"
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="android.widget.FrameLayout">'
        '<node class="android.widget.Button" text="Login" resource-id="com.demo:id/login" bounds="[10,20][110,60]" clickable="true" />'
        '<node class="android.widget.EditText" text="hello field" resource-id="com.demo:id/input" bounds="[20,80][220,140]" clickable="true" focused="true" />'
        "</node>"
        "</hierarchy>"
    )
    backend.select.return_value = element_handle

    service = create_xpath_service(backend)

    service.click("@com.demo:id/login", timeout=2.5)
    assert service.get_text("//Button") == "Login"
    assert service.exists("%Login%") is True
    service.set_text("hello%", "hello")

    backend.click.assert_called_once_with(60, 40)
    backend.select.assert_called_once_with(
        {
            "resourceId": "com.demo:id/input",
            "className": "android.widget.EditText",
            "text": "hello field",
        }
    )
    element_handle.set_text.assert_called_once_with("hello", timeout=0.0)


def test_xpath_service_sets_text_via_click_delete_and_send_keys_on_harmony_richeditor():
    backend = Mock()
    backend.platform = "harmony"
    backend.backend_name = "mock-harmony"
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="Root">'
        '<node class="RichEditor" text="388327" resource-id="title_area_NoteEditorManager" bounds="[10,20][210,80]" clickable="true" />'
        '<node class="RichEditor" text="388327" resource-id="content_area_NoteEditorManager" bounds="[20,120][220,220]" clickable="true" />'
        "</node>"
        "</hierarchy>"
    )

    service = create_xpath_service(backend)

    service.set_text("//RichEditor[@resource-id='content_area_NoteEditorManager']", "hello")

    backend.click.assert_called_once_with(210, 136)
    assert backend.press.call_count == len("388327")
    backend.press.assert_called_with("delete")
    backend.send_keys.assert_called_once_with("hello", clear=False)
    backend.select.assert_not_called()


def test_xpath_service_sets_text_via_click_delete_and_send_keys_on_harmony_textinput():
    backend = Mock()
    backend.platform = "harmony"
    backend.backend_name = "mock-harmony"
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="Root">'
        '<node class="TextInput" text="existing" resource-id="content_input" bounds="[20,120][220,220]" clickable="true" />'
        "</node>"
        "</hierarchy>"
    )

    service = create_xpath_service(backend)

    service.set_text("//TextInput[@resource-id='content_input']", "hello")

    backend.click.assert_called_once_with(210, 136)
    assert backend.press.call_count == len("existing")
    backend.press.assert_called_with("delete")
    backend.send_keys.assert_called_once_with("hello", clear=False)
    backend.select.assert_not_called()


def test_xpath_service_keeps_generic_click_and_send_keys_path_for_other_harmony_nodes():
    backend = Mock()
    backend.platform = "harmony"
    backend.backend_name = "mock-harmony"
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="Root">'
        '<node class="SearchChip" text="existing" resource-id="content_input" bounds="[20,120][220,220]" clickable="true" />'
        "</node>"
        "</hierarchy>"
    )

    service = create_xpath_service(backend)

    service.set_text("//SearchChip[@resource-id='content_input']", "hello")

    backend.click.assert_called_once_with(120, 170)
    backend.send_keys.assert_called_once_with("hello", clear=True)
    backend.press.assert_not_called()
    backend.select.assert_not_called()


def test_xpath_service_exposes_harmony_locator_mapping():
    parsed = parse_xpath_expression("@EntryBundle:id/login")
    resolved = resolve_xpath_for_platform(parsed, "harmony")

    assert resolved.platform == "harmony"
    assert resolved.strategy == "id"
    assert resolved.value == "EntryBundle:id/login"
    assert resolved.capability_boundary.name == "harmony_locator_v1"
    assert resolved.capability_boundary.required_strategies == HARMONY_REQUIRED_LOCATOR_STRATEGIES
    assert "must support the full locator set" in resolved.capability_boundary.note

    text_resolved = resolve_xpath_for_platform(parse_xpath_expression("Login"), "harmony")
    assert text_resolved.strategy == "text"
    assert text_resolved.value == "Login"
    assert text_resolved.capability_boundary == resolved.capability_boundary

    regex_resolved = resolve_xpath_for_platform(parse_xpath_expression("^Log.*"), "harmony")
    assert regex_resolved.strategy == "text_regex"
    assert regex_resolved.value == "^Log.*"


def test_harmony_boundary_reports_missing_locator_strategies():
    resolved = resolve_xpath_for_platform(parse_xpath_expression("Login"), "harmony")

    missing = missing_required_locator_strategies(
        resolved.capability_boundary,
        {"xpath", "id", "text", "text_contains"},
    )

    assert missing == {"text_regex", "text_startswith", "text_endswith"}


def test_xpath_commands_use_service():
    runner = CliRunner()
    backend = Mock()
    xpath_service = Mock()
    xpath_service.get_text.return_value = "Login"
    xpath_service.exists.return_value = True

    with patch("u2cli.element.connect_backend", return_value=backend), patch(
        "u2cli.element.create_xpath_service", return_value=xpath_service
    ) as mock_factory, patch("u2cli.element.output_result") as mock_output:
        result_click = runner.invoke(cmd_xpath_click, ["//Button"])
        result_get_text = runner.invoke(cmd_xpath_get_text, ["//Button"])
        result_exists = runner.invoke(cmd_xpath_exists, ["//Button"])
        result_set_text = runner.invoke(cmd_xpath_set_text, ["//Button", "hello"])

    assert result_click.exit_code == 0
    assert result_get_text.exit_code == 0
    assert result_exists.exit_code == 0
    assert result_set_text.exit_code == 0
    assert mock_factory.call_count == 4
    xpath_service.click.assert_called_once_with("//Button", timeout=3.0)
    xpath_service.get_text.assert_called_once_with("//Button")
    xpath_service.exists.assert_called_once_with("//Button")
    xpath_service.set_text.assert_called_once_with("//Button", "hello")
    assert mock_output.call_count == 4


def test_xpath_commands_run_on_harmony_once_normalized_service_is_available():
    runner = CliRunner()
    backend = SimpleNamespace(platform="harmony")
    xpath_service = Mock()

    with patch("u2cli.element.connect_backend", return_value=backend), patch(
        "u2cli.element.create_xpath_service", return_value=xpath_service
    ) as mock_factory, patch("u2cli.element.output_result") as mock_output:
        result = runner.invoke(cmd_xpath_click, ["//Button"])

    assert result.exit_code == 0
    mock_factory.assert_called_once_with(backend)
    xpath_service.click.assert_called_once_with("//Button", timeout=3.0)
    mock_output.assert_called_once_with(None, "d.xpath('//Button').click(timeout=3.0)")


def test_screen_commands_use_backend_api(tmp_path):
    runner = CliRunner()
    fake_image = FakeImage()
    shell_result = SimpleNamespace(output="ok", exit_code=0)
    backend = Mock()
    backend.device_info.return_value = {"model": "Pixel"}
    backend.ui_info.return_value = {"currentPackageName": "com.demo"}
    backend.screenshot.return_value = fake_image
    backend.window_size.return_value = (1080, 2400)
    backend.shell.return_value = shell_result
    backend.current_app.return_value = {"package": "com.demo", "activity": "MainActivity"}
    backend.get_orientation.return_value = "natural"

    with patch("u2cli.screen.connect_backend", return_value=backend), patch("u2cli.screen.output_result") as mock_output:
        result_device_info = runner.invoke(cmd_device_info, [])
        result_ui_info = runner.invoke(cmd_ui_info, [])
        screenshot_path = tmp_path / "screen.png"
        result_screenshot = runner.invoke(cmd_screenshot, [str(screenshot_path)])
        result_window_size = runner.invoke(cmd_window_size, [])
        result_screen_on = runner.invoke(cmd_screen_on, [])
        result_screen_off = runner.invoke(cmd_screen_off, [])
        result_orientation_get = runner.invoke(cmd_orientation, [])
        result_orientation_set = runner.invoke(cmd_orientation, ["--set", "left"])
        result_press = runner.invoke(cmd_press, ["back"])
        result_swipe = runner.invoke(cmd_swipe, ["0.1", "0.2", "0.8", "0.9"])
        result_swipe_ext = runner.invoke(cmd_swipe_ext, ["up"])
        result_click_coord = runner.invoke(cmd_click_coord, ["10", "20"])
        result_double_click = runner.invoke(cmd_double_click, ["10", "20"])
        result_long_click_coord = runner.invoke(cmd_long_click_coord, ["10", "20"])
        result_send_keys = runner.invoke(cmd_send_keys, ["hello"])
        result_open_notification = runner.invoke(cmd_open_notification, [])
        result_open_quick_settings = runner.invoke(cmd_open_quick_settings, [])
        result_open_url = runner.invoke(cmd_open_url, ["https://example.com"])
        result_shell = runner.invoke(cmd_shell, ["echo", "ok"])
        result_current_app = runner.invoke(cmd_current_app, [])
        result_media_control = runner.invoke(cmd_media_control, ["play-pause"])

    assert result_device_info.exit_code == 0
    assert result_ui_info.exit_code == 0
    assert result_screenshot.exit_code == 0
    assert result_window_size.exit_code == 0
    assert result_screen_on.exit_code == 0
    assert result_screen_off.exit_code == 0
    assert result_orientation_get.exit_code == 0
    assert result_orientation_set.exit_code == 0
    assert result_press.exit_code == 0
    assert result_swipe.exit_code == 0
    assert result_swipe_ext.exit_code == 0
    assert result_click_coord.exit_code == 0
    assert result_double_click.exit_code == 0
    assert result_long_click_coord.exit_code == 0
    assert result_send_keys.exit_code == 0
    assert result_open_notification.exit_code == 0
    assert result_open_quick_settings.exit_code == 0
    assert result_open_url.exit_code == 0
    assert result_shell.exit_code == 0
    assert result_current_app.exit_code == 0
    assert result_media_control.exit_code == 0
    backend.device_info.assert_called_once_with()
    backend.ui_info.assert_called_once_with()
    backend.screenshot.assert_called_once_with()
    backend.window_size.assert_called_once_with()
    backend.screen_on.assert_called_once_with()
    backend.screen_off.assert_called_once_with()
    backend.get_orientation.assert_called_once_with()
    backend.set_orientation.assert_called_once_with("left")
    backend.press.assert_called_once_with("back")
    backend.swipe.assert_called_once_with(0.1, 0.2, 0.8, 0.9, duration=0.5)
    backend.swipe_ext.assert_called_once_with("up", scale=0.8)
    backend.click.assert_called_once_with(10.0, 20.0)
    backend.double_click.assert_called_once_with(10.0, 20.0, duration=0.1)
    backend.long_click.assert_called_once_with(10.0, 20.0, duration=0.5)
    backend.send_keys.assert_called_once_with("hello", clear=True)
    backend.open_notification.assert_called_once_with()
    backend.open_quick_settings.assert_called_once_with()
    backend.open_url.assert_called_once_with("https://example.com")
    backend.shell.assert_called_once_with("echo ok", timeout=60)
    backend.current_app.assert_called_once_with()
    backend.media_control.assert_called_once_with("play-pause")
    assert fake_image.saved_to is not None
    assert mock_output.call_count == 21


def test_hierarchy_service_normalizes_backend_dump():
    backend = Mock(platform="android", backend_name="uiautomator2")
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="android.widget.FrameLayout">'
        '<node class="android.widget.TextView" text="Login" bounds="[0,0][100,40]" clickable="true" />'
        "</node>"
        "</hierarchy>"
    )

    hierarchy = create_hierarchy_service(backend).dump(compressed=True, max_depth=2)

    backend.dump_hierarchy_xml.assert_called_once_with(compressed=True, max_depth=2)
    assert hierarchy.output_format == "text"
    assert hierarchy.platform == "android"
    assert hierarchy.backend_name == "uiautomator2"
    assert hierarchy.raw_xml.startswith("<hierarchy>")
    assert hierarchy.content == 'TextView "Login" [0,0,100,40] click'


def test_dump_hierarchy_command_uses_service(tmp_path):
    runner = CliRunner()
    backend = Mock()
    hierarchy_service = Mock()
    hierarchy_service.dump.return_value.content = "TextView \"Login\""

    with patch("u2cli.screen.connect_backend", return_value=backend), patch(
        "u2cli.screen.create_hierarchy_service", return_value=hierarchy_service
    ) as mock_factory, patch("u2cli.screen.output_result") as mock_output:
        output_file = tmp_path / "hierarchy.txt"
        result = runner.invoke(cmd_dump_hierarchy, ["--compressed", "--max-depth", "3", "--output", str(output_file)])

    assert result.exit_code == 0
    mock_factory.assert_called_once_with(backend)
    hierarchy_service.dump.assert_called_once_with(compressed=True, max_depth=3, raw=False)
    assert output_file.read_text(encoding="utf-8") == 'TextView "Login"'
    mock_output.assert_called_once()


def test_harmony_dump_hierarchy_command_uses_normalized_output_without_partial_marker():
    runner = CliRunner()
    backend = SimpleNamespace(platform="harmony")
    hierarchy_service = Mock()
    hierarchy_service.dump.return_value = SimpleNamespace(content="tree", raw_xml="<hierarchy />")

    with patch("u2cli.screen.connect_backend", return_value=backend), patch(
        "u2cli.screen.create_hierarchy_service", return_value=hierarchy_service
    ), patch("u2cli.screen.output_result") as mock_output:
        result = runner.invoke(cmd_dump_hierarchy, [])

    assert result.exit_code == 0
    mock_output.assert_called_once_with("tree", "d.dump_hierarchy()")


def test_xpath_service_supports_normalized_full_xpath_predicates_and_positions():
    backend = Mock()
    backend.platform = "harmony"
    backend.dump_hierarchy_xml.return_value = (
        "<hierarchy>"
        '<node class="RootLayout">'
        '<node class="Button" text="Login" content-desc="Primary action" resource-id="entry.login.primary" bounds="[0,0][50,50]" clickable="true" />'
        '<node class="Button" text="Login" content-desc="Secondary action" resource-id="entry.login.secondary" bounds="[60,0][110,50]" clickable="true" />'
        "</node>"
        "</hierarchy>"
    )

    service = create_xpath_service(backend)

    assert service.get_text("//Button[contains(@content-desc, 'Primary')]") == "Login"
    assert service.exists("//Button[@resource-id='entry.login.secondary'][1]") is True
    service.click("//Button[@text='Login'][2]")

    backend.click.assert_called_once_with(85, 25)


def test_harmony_system_panel_commands_mark_best_effort_support():
    runner = CliRunner()
    backend = Mock()
    backend.platform = "harmony"

    with patch("u2cli.screen.connect_backend", return_value=backend), patch(
        "u2cli.screen.output_result"
    ) as mock_output:
        notification_result = runner.invoke(cmd_open_notification, [])
        quick_settings_result = runner.invoke(cmd_open_quick_settings, [])

    assert notification_result.exit_code == 0
    assert quick_settings_result.exit_code == 0
    backend.open_notification.assert_called_once_with()
    backend.open_quick_settings.assert_called_once_with()
    assert mock_output.call_args_list[0].kwargs["extra"] == {
        "partial": True,
        "support_level": "partial",
        "note": "Harmony open-notification currently uses a best-effort gesture recipe with desktop-state retry, but without strict panel-state verification.",
        "verification": "best_effort",
    }
    assert mock_output.call_args_list[1].kwargs["extra"] == {
        "partial": True,
        "support_level": "partial",
        "note": "Harmony open-quick-settings currently uses a best-effort gesture recipe without panel-state verification.",
        "verification": "best_effort",
    }


def test_app_commands_use_backend_api():
    runner = CliRunner()
    backend = Mock()
    backend.app_wait.return_value = 123
    backend.app_uninstall.return_value = True
    backend.app_info.return_value = {"versionName": "1.0.0"}
    backend.app_list.return_value = ["com.demo"]
    backend.app_list_running.return_value = ["com.demo"]

    with patch("u2cli.app.connect_backend", return_value=backend), patch("u2cli.app.output_result") as mock_output:
        result_start = runner.invoke(cmd_app_start, ["--activity", "MainActivity", "--wait", "com.demo"])
        result_stop = runner.invoke(cmd_app_stop, ["com.demo"])
        result_clear = runner.invoke(cmd_app_clear, ["com.demo"])
        result_install = runner.invoke(cmd_app_install, ["demo.apk"])
        result_uninstall = runner.invoke(cmd_app_uninstall, ["com.demo"])
        result_info = runner.invoke(cmd_app_info, ["com.demo"])
        result_list = runner.invoke(cmd_app_list, [])
        result_list_running = runner.invoke(cmd_app_list_running, [])
        result_wait = runner.invoke(cmd_app_wait, ["--front", "com.demo"])

    assert result_start.exit_code == 0
    assert result_stop.exit_code == 0
    assert result_clear.exit_code == 0
    assert result_install.exit_code == 0
    assert result_uninstall.exit_code == 0
    assert result_info.exit_code == 0
    assert result_list.exit_code == 0
    assert result_list_running.exit_code == 0
    assert result_wait.exit_code == 0
    backend.app_start.assert_called_once_with("com.demo", activity="MainActivity", wait=True)
    backend.app_stop.assert_called_once_with("com.demo")
    backend.app_clear.assert_called_once_with("com.demo")
    backend.app_install.assert_called_once_with("demo.apk")
    backend.app_uninstall.assert_called_once_with("com.demo")
    backend.app_info.assert_called_once_with("com.demo")
    backend.app_list.assert_called_once_with("")
    backend.app_list_running.assert_called_once_with()
    backend.app_wait.assert_called_once_with("com.demo", timeout=20.0, front=True)
    assert mock_output.call_count == 9


def test_harmony_app_install_and_uninstall_are_gated_until_artifact_model_is_normalized():
    runner = CliRunner()
    backend = SimpleNamespace(platform="harmony")

    with patch("u2cli.app.connect_backend", return_value=backend):
        install_result = runner.invoke(cmd_app_install, ["demo.hap"])
        uninstall_result = runner.invoke(cmd_app_uninstall, ["com.demo.app"])

    assert install_result.exit_code != 0
    assert uninstall_result.exit_code != 0
    assert "app-install is not yet supported on Harmony" in install_result.output
    assert "app-uninstall is not yet supported on Harmony" in uninstall_result.output


def test_harmony_app_metadata_commands_mark_results_partial():
    runner = CliRunner()
    backend = Mock()
    backend.platform = "harmony"
    backend.app_info.return_value = {"name": "Demo"}
    backend.app_list.return_value = ["com.demo.app"]
    backend.app_list_running.return_value = ["com.demo.app"]

    with patch("u2cli.app.connect_backend", return_value=backend), patch("u2cli.app.output_result") as mock_output:
        info_result = runner.invoke(cmd_app_info, ["com.demo.app"])
        list_result = runner.invoke(cmd_app_list, [])
        running_result = runner.invoke(cmd_app_list_running, [])

    assert info_result.exit_code == 0
    assert list_result.exit_code == 0
    assert running_result.exit_code == 0
    assert mock_output.call_args_list[0].kwargs["extra"] == {
        "partial": True,
        "support_level": "partial",
        "note": "Harmony app-info currently returns a pre-normalized compatibility payload; the unified app service schema is still pending.",
    }
    assert mock_output.call_args_list[1].kwargs["extra"] == {
        "partial": True,
        "support_level": "partial",
        "note": "Harmony app-list currently exposes a pre-normalized compatibility view and may differ from the final cross-platform app inventory semantics.",
    }
    assert mock_output.call_args_list[2].kwargs["extra"] == {
        "partial": True,
        "support_level": "partial",
        "note": "Harmony app-list-running currently reports a reduced compatibility view rather than a normalized running app model.",
    }