from types import SimpleNamespace
from unittest.mock import patch

from u2cli.transports.hdc import run_hdc_shell


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