import logging
import unittest
from unittest.mock import patch

from u2cli import daemon


class DaemonRetryTests(unittest.TestCase):
    def test_default_daemon_retries_once_when_bound_device_is_missing(self) -> None:
        logger = logging.getLogger("test-daemon")

        with patch("u2cli.daemon._run_cli_once") as mock_run, patch(
            "u2cli.device.default_device_serial",
            return_value="A",
        ), patch("u2cli.device.clear_cached_device") as mock_clear:
            mock_run.side_effect = [
                (1, "", '{"error": "device \'A\' not found", "type": "AdbError"}\n', RuntimeError("device 'A' not found")),
                (0, "ok\n", "", None),
            ]

            exit_code, stdout_value, stderr_value = daemon._run_cli_with_default_retry(None, ["device-info"], logger)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_value, "ok\n")
        self.assertEqual(stderr_value, "")
        mock_clear.assert_called_once_with()
        self.assertEqual(mock_run.call_count, 2)

    def test_default_daemon_does_not_retry_for_non_device_errors(self) -> None:
        logger = logging.getLogger("test-daemon")

        with patch("u2cli.daemon._run_cli_once", return_value=(1, "", '{"error": "element not found", "type": "UiObjectNotFoundError"}\n', RuntimeError("element not found"))) as mock_run, patch(
            "u2cli.device.default_device_serial",
            return_value="A",
        ), patch("u2cli.device.clear_cached_device") as mock_clear:
            exit_code, stdout_value, stderr_value = daemon._run_cli_with_default_retry(None, ["click"], logger)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_value, "")
        self.assertIn("element not found", stderr_value)
        mock_clear.assert_not_called()
        mock_run.assert_called_once()

    def test_harmony_cached_backend_retries_once_for_transport_error(self) -> None:
        logger = logging.getLogger("test-daemon")

        with patch("u2cli.daemon._run_cli_once") as mock_run, patch(
            "u2cli.device.default_device_serial",
            return_value=None,
        ), patch("u2cli.device.has_cached_backend", return_value=True), patch(
            "u2cli.device.clear_cached_device"
        ) as mock_clear:
            mock_run.side_effect = [
                (
                    1,
                    "",
                    '{"error": "No devices found. Please connect a device.", "type": "DeviceNotFoundError"}\n',
                    SystemExit(1),
                ),
                (0, "ok\n", "", None),
            ]

            exit_code, stdout_value, stderr_value = daemon._run_cli_with_default_retry(
                "HDC-1",
                ["current-app"],
                logger,
                platform="harmony",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_value, "ok\n")
        self.assertEqual(stderr_value, "")
        mock_clear.assert_called_once_with("HDC-1", platform="harmony")
        self.assertEqual(mock_run.call_count, 2)

    def test_harmony_cached_backend_does_not_retry_for_non_transport_error(self) -> None:
        logger = logging.getLogger("test-daemon")

        with patch(
            "u2cli.daemon._run_cli_once",
            return_value=(
                1,
                "",
                '{"error": "element not found", "type": "RuntimeError"}\n',
                RuntimeError("element not found"),
            ),
        ) as mock_run, patch("u2cli.device.default_device_serial", return_value=None), patch(
            "u2cli.device.has_cached_backend",
            return_value=True,
        ), patch("u2cli.device.clear_cached_device") as mock_clear:
            exit_code, stdout_value, stderr_value = daemon._run_cli_with_default_retry(
                "HDC-1",
                ["click"],
                logger,
                platform="harmony",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_value, "")
        self.assertIn("element not found", stderr_value)
        mock_clear.assert_not_called()
        mock_run.assert_called_once()

    def test_harmony_without_cached_backend_does_not_retry_transport_error(self) -> None:
        logger = logging.getLogger("test-daemon")

        with patch(
            "u2cli.daemon._run_cli_once",
            return_value=(
                1,
                "",
                '{"error": "No devices found. Please connect a device.", "type": "DeviceNotFoundError"}\n',
                SystemExit(1),
            ),
        ) as mock_run, patch("u2cli.device.default_device_serial", return_value=None), patch(
            "u2cli.device.has_cached_backend",
            return_value=False,
        ), patch("u2cli.device.clear_cached_device") as mock_clear:
            exit_code, stdout_value, stderr_value = daemon._run_cli_with_default_retry(
                "HDC-1",
                ["current-app"],
                logger,
                platform="harmony",
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout_value, "")
        self.assertIn("No devices found", stderr_value)
        mock_clear.assert_not_called()
        mock_run.assert_called_once()

    def test_run_via_daemon_passes_platform_context(self) -> None:
        with patch("u2cli.daemon.start_daemon", return_value=(True, "started")) as mock_start, patch(
            "u2cli.daemon.send_request",
            return_value={"ok": True, "exit_code": 0, "stdout": "", "stderr": ""},
        ) as mock_send:
            exit_code = daemon.run_via_daemon("SERIAL-A", "android", ["click"])

        self.assertEqual(exit_code, 0)
        mock_start.assert_called_once_with("SERIAL-A", platform="android", full_output_log=False)
        mock_send.assert_called_once_with(
            "SERIAL-A",
            {"action": "run", "argv": ["click"], "platform": "android"},
            timeout=300.0,
            platform="android",
        )

    def test_start_daemon_reuses_running_process_when_fingerprint_matches(self) -> None:
        with patch("u2cli.daemon.current_code_fingerprint", return_value="fresh"), patch(
            "u2cli.daemon.daemon_status",
            return_value={"running": True, "code_fingerprint": "fresh"},
        ) as mock_status, patch("u2cli.daemon.stop_daemon") as mock_stop, patch("u2cli.daemon.subprocess.Popen") as mock_popen:
            ok, message = daemon.start_daemon("SERIAL-A", platform="harmony")

        self.assertTrue(ok)
        self.assertEqual(message, "u2cli daemon is already running")
        mock_status.assert_called_once_with("SERIAL-A", platform="harmony")
        mock_stop.assert_not_called()
        mock_popen.assert_not_called()

    def test_start_daemon_restarts_running_process_when_fingerprint_differs(self) -> None:
        with patch("u2cli.daemon.current_code_fingerprint", return_value="fresh"), patch(
            "u2cli.daemon.daemon_status",
            return_value={"running": True, "code_fingerprint": "stale"},
        ), patch("u2cli.daemon.stop_daemon", return_value=(True, "stopped")) as mock_stop, patch(
            "u2cli.daemon.is_running",
            side_effect=[False, True],
        ) as mock_running, patch("u2cli.daemon.subprocess.Popen") as mock_popen:
            ok, message = daemon.start_daemon("SERIAL-A", platform="harmony", timeout=0.5)

        self.assertTrue(ok)
        self.assertEqual(message, "u2cli daemon started")
        mock_stop.assert_called_once_with("SERIAL-A", platform="harmony")
        self.assertEqual(mock_running.call_count, 2)
        mock_popen.assert_called_once()

    def test_daemon_status_reports_code_fingerprint_from_ping(self) -> None:
        with patch("u2cli.daemon.is_running", return_value=True), patch(
            "u2cli.daemon.send_request",
            return_value={
                "ok": True,
                "pid": 1234,
                "full_output_log": False,
                "code_fingerprint": "fresh",
                "started_at": 100,
                "last_request_at": 120,
                "request_count": 3,
                "backend_cached": True,
                "active_device_id": "SERIAL-A",
            },
        ):
            status = daemon.daemon_status("SERIAL-A", platform="android")

        self.assertTrue(status["running"])
        self.assertEqual(status["code_fingerprint"], "fresh")
        self.assertEqual(status["started_at"], 100)
        self.assertEqual(status["last_request_at"], 120)
        self.assertEqual(status["request_count"], 3)
        self.assertTrue(status["backend_cached"])
        self.assertEqual(status["active_device_id"], "SERIAL-A")

    def test_daemon_runtime_snapshot_includes_minimal_diagnostic_fields(self) -> None:
        runtime_state = {"started_at": 100, "last_request_at": 120, "request_count": 4}

        with patch("u2cli.daemon.os.getpid", return_value=4321), patch(
            "u2cli.device.has_cached_backend",
            return_value=True,
        ), patch("u2cli.daemon._active_device_id", return_value="SERIAL-A"):
            snapshot = daemon._daemon_runtime_snapshot(
                "SERIAL-A",
                platform="android",
                full_output_log=False,
                code_fingerprint="fresh",
                runtime_state=runtime_state,
            )

        self.assertEqual(
            snapshot,
            {
                "ok": True,
                "pid": 4321,
                "full_output_log": False,
                "code_fingerprint": "fresh",
                "started_at": 100,
                "last_request_at": 120,
                "request_count": 4,
                "backend_cached": True,
                "active_device_id": "SERIAL-A",
            },
        )

    def test_restart_daemon_stops_then_starts_target(self) -> None:
        with patch("u2cli.daemon.stop_daemon", return_value=(True, "stopped")) as mock_stop, patch(
            "u2cli.daemon.start_daemon",
            return_value=(True, "started"),
        ) as mock_start:
            ok, message = daemon.restart_daemon("SERIAL-A", platform="android", full_output_log=True)

        self.assertTrue(ok)
        self.assertEqual(message, "started")
        mock_stop.assert_called_once_with("SERIAL-A", platform="android")
        mock_start.assert_called_once_with(
            "SERIAL-A",
            platform="android",
            timeout=6.0,
            full_output_log=True,
        )

    def test_platform_specific_daemon_paths_do_not_collide(self) -> None:
        self.assertNotEqual(
            daemon.socket_path("SERIAL-A", platform="android"),
            daemon.socket_path("SERIAL-A", platform="harmony"),
        )
        self.assertNotEqual(
            daemon.pid_path("SERIAL-A", platform="android"),
            daemon.pid_path("SERIAL-A", platform="harmony"),
        )
        self.assertNotEqual(
            daemon.log_path("SERIAL-A", platform="android"),
            daemon.log_path("SERIAL-A", platform="harmony"),
        )
