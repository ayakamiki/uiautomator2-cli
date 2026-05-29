from types import SimpleNamespace
from unittest.mock import Mock, patch

from u2cli.transports.hdc import connect_harmony_driver, run_hdc_shell, _wait_for_harmony_target


def test_run_hdc_shell_respects_hdc_bin_env_and_serial():
    with patch.dict("os.environ", {"HDC_BIN": "hdc-custom"}, clear=False), patch(
        "u2cli.transports.hdc.shutil.which", return_value="/tmp/hdc-custom"
    ), patch("u2cli.transports.hdc.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="No Error", stderr="")
        result = run_hdc_shell(["uitest", "uiInput", "keyEvent", "10"], serial="HDC-1", timeout=15.0)

    assert result.returncode == 0
    mock_run.assert_called_once_with(
        ["hdc-custom", "-t", "HDC-1", "shell", "uitest", "uiInput", "keyEvent", "10"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15.0,
    )


def test_connect_harmony_driver_releases_stale_driver_singleton_before_reconnect():
    stale_client = Mock()

    class FakeDriver:
        _instance = {}

        def __new__(cls, serial):
            cached = cls._instance.get(serial)
            if cached is not None:
                return cached
            instance = super().__new__(cls)
            cls._instance[serial] = instance
            return instance

        def __init__(self, serial):
            self.serial = serial
            self.created = True
            if not hasattr(self, "_client"):
                self._client = Mock()

    stale_driver = object.__new__(FakeDriver)
    stale_driver.serial = "HDC-1"
    stale_driver._client = stale_client
    FakeDriver._instance["HDC-1"] = stale_driver

    with patch("u2cli.transports.hdc._load_hmdriver2_driver", return_value=FakeDriver), patch(
        "u2cli.transports.hdc.ensure_hdc_available", return_value="hdc"
    ), patch("u2cli.transports.hdc.list_targets", return_value=["HDC-1"]):
        driver = connect_harmony_driver("HDC-1")

    stale_client.release.assert_called_once_with()
    assert driver is not stale_driver
    assert driver.serial == "HDC-1"
    assert FakeDriver._instance["HDC-1"] is driver


def test_wait_for_harmony_target_retries_until_serial_reappears():
    with patch("u2cli.transports.hdc.list_targets", side_effect=[[], ["HDC-1"]]), patch(
        "u2cli.transports.hdc.time.monotonic", side_effect=[0.0, 0.0, 0.1]
    ), patch("u2cli.transports.hdc.time.sleep") as mock_sleep:
        _wait_for_harmony_target("HDC-1", timeout=1.0, interval=0.1)

    mock_sleep.assert_called_once_with(0.1)


def test_connect_harmony_driver_retries_bootstrap_after_target_missing_error():
    class FakeDriver:
        _instance = {}
        call_count = 0

        def __new__(cls, serial):
            cls.call_count += 1
            if cls.call_count == 1:
                raise RuntimeError("No devices found. Please connect a device.")
            instance = super().__new__(cls)
            cls._instance[serial] = instance
            return instance

        def __init__(self, serial):
            self.serial = serial
            self._client = Mock()

    with patch("u2cli.transports.hdc._load_hmdriver2_driver", return_value=FakeDriver), patch(
        "u2cli.transports.hdc.ensure_hdc_available", return_value="hdc"
    ), patch(
        "u2cli.transports.hdc.list_targets",
        side_effect=[["HDC-1"], [], ["HDC-1"]],
    ), patch(
        "u2cli.transports.hdc.time.monotonic", side_effect=[0.0, 0.0, 0.1]
    ), patch("u2cli.transports.hdc.time.sleep"):
        driver = connect_harmony_driver("HDC-1")

    assert driver.serial == "HDC-1"
    assert FakeDriver.call_count == 2