import json
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from u2cli import device


class ConnectDeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        device._DEVICE_CACHE.clear()
        device._DEFAULT_DEVICE_SERIAL = None

    def tearDown(self) -> None:
        device._DEVICE_CACHE.clear()
        device._DEFAULT_DEVICE_SERIAL = None

    def test_default_device_sticks_until_cleared(self) -> None:
        first_device = object()
        second_device = object()

        with patch("u2cli.device.click.get_current_context", return_value=None), patch(
            "u2cli.device.adbutils.adb.device",
            side_effect=[
                SimpleNamespace(serial="A"),
                SimpleNamespace(serial="B"),
            ],
        ), patch("u2cli.device.u2.connect", side_effect=[first_device, second_device]) as mock_connect:
            self.assertIs(device.connect_device(), first_device)
            self.assertIs(device.connect_device(), first_device)
            device.clear_cached_device()
            self.assertIs(device.connect_device(), second_device)

        self.assertEqual(mock_connect.call_args_list, [call("A"), call("B")])

    def test_default_device_preserves_normal_unique_device_errors(self) -> None:
        with patch("u2cli.device.click.get_current_context", return_value=None), patch(
            "u2cli.device.adbutils.adb.device",
            side_effect=RuntimeError("more than one device/emulator"),
        ), patch("u2cli.device.click.echo") as mock_echo:
            with self.assertRaises(SystemExit) as exc:
                device.connect_device()

        self.assertEqual(exc.exception.code, 1)
        payload = json.loads(mock_echo.call_args.args[0])
        self.assertEqual(payload["type"], "RuntimeError")
        self.assertIn("more than one device/emulator", payload["error"])

    def test_explicit_serial_still_uses_serial_cache(self) -> None:
        connected_device = object()

        with patch("u2cli.device.adbutils.adb.device") as mock_adb_device, patch(
            "u2cli.device.u2.connect", return_value=connected_device
        ) as mock_connect:
            self.assertIs(device.connect_device("SERIAL-A"), connected_device)
            self.assertIs(device.connect_device("SERIAL-A"), connected_device)

        mock_adb_device.assert_not_called()
        mock_connect.assert_called_once_with("SERIAL-A")

    def test_connect_backend_wraps_android_device_and_uses_backend_cache(self) -> None:
        connected_device = object()

        with patch("u2cli.device._connect_raw_device", return_value=connected_device) as mock_connect:
            backend = device.connect_backend("SERIAL-A", platform="android")
            cached_backend = device.connect_backend("SERIAL-A", platform="android")

        self.assertIs(backend, cached_backend)
        self.assertEqual(backend.platform, "android")
        self.assertEqual(backend.backend_name, "uiautomator2")
        self.assertIs(backend.raw_device(), connected_device)
        mock_connect.assert_called_once_with("android", "SERIAL-A")

    def test_connect_backend_wraps_harmony_driver_and_uses_platform_connector(self) -> None:
        connected_driver = object()

        with patch("u2cli.device._connect_raw_device", return_value=connected_driver) as mock_connect:
            backend = device.connect_backend("HDC-DEVICE", platform="harmony")
            cached_backend = device.connect_backend("HDC-DEVICE", platform="harmony")

        self.assertIs(backend, cached_backend)
        self.assertEqual(backend.platform, "harmony")
        self.assertEqual(backend.backend_name, "hmdriver2+hdc")
        self.assertIs(backend.raw_device(), connected_driver)
        mock_connect.assert_called_once_with("harmony", "HDC-DEVICE")
