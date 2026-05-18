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
