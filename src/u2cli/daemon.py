"""Background daemon for adb-server style command execution.

The daemon keeps a warm Python process so device connection can be reused
across multiple CLI invocations.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

import click


ENV_IN_DAEMON = "U2CLI_IN_DAEMON"
ENV_DAEMON_LOG_FILE = "U2CLI_DAEMON_LOG_FILE"
ENV_DAEMON_LOG_FULL_OUTPUT = "U2CLI_DAEMON_LOG_FULL_OUTPUT"
_DEFAULT_DEVICE_MISSING_PATTERNS = (
    re.compile(r"device\s+'.+?'\s+not\s+found", re.IGNORECASE),
    re.compile(r"device\s+.+?\s+not\s+found", re.IGNORECASE),
    re.compile(r"no\s+device", re.IGNORECASE),
    re.compile(r"transport.*not\s+found", re.IGNORECASE),
)


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _serial_token(serial: Optional[str]) -> str:
    if not serial:
        return "default"
    digest = hashlib.sha1(serial.encode("utf-8")).hexdigest()[:10]
    return f"s-{digest}"


def socket_path(serial: Optional[str]) -> str:
    return os.path.join(tempfile.gettempdir(), f"u2cli-daemon-{_serial_token(serial)}.sock")


def pid_path(serial: Optional[str]) -> str:
    return os.path.join(tempfile.gettempdir(), f"u2cli-daemon-{_serial_token(serial)}.pid")


def log_dir() -> str:
    path = os.path.join(os.path.expanduser("~"), ".u2cli", "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_path(serial: Optional[str]) -> str:
    return os.path.join(log_dir(), f"u2cli-daemon-{_serial_token(serial)}.log")


def _daemon_logger(serial: Optional[str]) -> logging.Logger:
    logger_name = f"u2cli.daemon.{_serial_token(serial)}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_path(serial),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s")
    )
    logger.addHandler(handler)

    # Share the same log sink for related modules (e.g. u2cli.device).
    namespace_logger = logging.getLogger("u2cli")
    if not namespace_logger.handlers:
        namespace_logger.setLevel(logging.INFO)
        namespace_logger.propagate = False
        namespace_logger.addHandler(handler)
    return logger


def read_log_tail(serial: Optional[str], lines: int = 200) -> str:
    path = log_path(serial)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    if lines <= 0:
        return ""
    return "".join(content[-lines:])


def _active_device_id(serial: Optional[str]) -> Optional[str]:
    if serial is not None:
        return serial

    from u2cli.device import default_device_serial

    return default_device_serial()


def _run_cli_once(serial: Optional[str], argv: list[str]) -> tuple[int, str, str, Optional[BaseException]]:
    stdout_io = io.StringIO()
    stderr_io = io.StringIO()
    exit_code = 0
    run_error: Optional[BaseException] = None

    with contextlib.redirect_stdout(stdout_io), contextlib.redirect_stderr(stderr_io):
        try:
            # Lazy import avoids circular import at module load time.
            from u2cli.cli import cli

            cli.main(
                args=argv,
                standalone_mode=False,
                obj={"serial": serial, "output_json": False},
            )
        except click.exceptions.Exit as e:
            exit_code = int(e.exit_code or 0)
            run_error = e
        except click.ClickException as e:
            click.echo(
                json.dumps({"error": e.format_message(), "type": type(e).__name__}, ensure_ascii=False),
                err=True,
            )
            exit_code = int(e.exit_code)
            run_error = e
        except SystemExit as e:
            run_error = e
            if isinstance(e.code, int):
                exit_code = e.code
            else:
                exit_code = 1
        except Exception as e:
            run_error = e
            click.echo(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False), err=True)
            exit_code = 1

    return exit_code, stdout_io.getvalue(), stderr_io.getvalue(), run_error


def _looks_like_missing_default_device(
    error: Optional[BaseException],
    stderr_value: str,
    bound_serial: Optional[str],
) -> bool:
    if not bound_serial:
        return False

    text = "\n".join(part for part in [str(error or ""), stderr_value] if part).lower()
    if bound_serial.lower() in text and "not found" in text:
        return True
    return any(pattern.search(text) for pattern in _DEFAULT_DEVICE_MISSING_PATTERNS)


def _run_cli_with_default_retry(
    serial: Optional[str],
    argv: list[str],
    logger: logging.Logger,
) -> tuple[int, str, str]:
    from u2cli.device import clear_cached_device, default_device_serial

    bound_default_serial = default_device_serial() if serial is None else None
    exit_code, stdout_value, stderr_value, run_error = _run_cli_once(serial, argv)

    if (
        serial is None
        and bound_default_serial
        and exit_code != 0
        and _looks_like_missing_default_device(run_error, stderr_value, bound_default_serial)
    ):
        logger.info("default device missing, clear sticky binding and retry once device_id=%r", bound_default_serial)
        clear_cached_device()
        exit_code, stdout_value, stderr_value, _ = _run_cli_once(serial, argv)

    return exit_code, stdout_value, stderr_value


def _recv_json(conn: socket.socket) -> Dict[str, Any]:
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
    if not raw:
        return {}
    return json.loads(raw)


def _send_json(conn: socket.socket, data: Dict[str, Any]) -> None:
    conn.sendall((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))


def send_request(serial: Optional[str], payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    sock_file = socket_path(serial)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(sock_file)
        _send_json(client, payload)
        return _recv_json(client)


def is_running(serial: Optional[str]) -> bool:
    sock_file = socket_path(serial)
    if not os.path.exists(sock_file):
        return False
    try:
        resp = send_request(serial, {"action": "ping"}, timeout=1.0)
        return bool(resp.get("ok"))
    except Exception:
        return False


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def serve(serial: Optional[str]) -> None:
    sock_file = socket_path(serial)
    pid_file = pid_path(serial)
    logger = _daemon_logger(serial)
    os.environ[ENV_DAEMON_LOG_FILE] = log_path(serial)
    full_output_logging = _env_true(ENV_DAEMON_LOG_FULL_OUTPUT)

    _remove_file(sock_file)
    os.environ[ENV_IN_DAEMON] = "1"

    stop_flag = {"stop": False}

    def _handle_stop(_signum, _frame):
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(sock_file)
        server.listen(16)
        server.settimeout(0.5)

        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        logger.info(
            "daemon started serial=%r device_id=%r socket=%s pid_file=%s full_output_logging=%s",
            serial,
            _active_device_id(serial),
            sock_file,
            pid_file,
            full_output_logging,
        )

        while not stop_flag["stop"]:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue

            with conn:
                try:
                    req = _recv_json(conn)
                    action = req.get("action")
                    logger.info("request action=%s device_id=%r", action, _active_device_id(serial))
                    if action == "ping":
                        _send_json(
                            conn,
                            {
                                "ok": True,
                                "pid": os.getpid(),
                                "full_output_log": full_output_logging,
                            },
                        )
                        continue
                    if action == "stop":
                        logger.info("request stop received device_id=%r", _active_device_id(serial))
                        _send_json(conn, {"ok": True})
                        stop_flag["stop"] = True
                        continue
                    if action != "run":
                        logger.warning("unknown action=%r device_id=%r", action, _active_device_id(serial))
                        _send_json(conn, {"ok": False, "error": "unknown action", "exit_code": 1})
                        continue

                    argv = req.get("argv") or []
                    logger.info(
                        "run start device_id=%r argv=%s",
                        _active_device_id(serial),
                        json.dumps(argv, ensure_ascii=False),
                    )
                    started_at = time.time()
                    exit_code, stdout_value, stderr_value = _run_cli_with_default_retry(serial, argv, logger)
                    duration_ms = int((time.time() - started_at) * 1000)
                    logger.info(
                        "run end device_id=%r exit_code=%s duration_ms=%s stdout_bytes=%s stderr_bytes=%s",
                        _active_device_id(serial),
                        exit_code,
                        duration_ms,
                        len(stdout_value.encode("utf-8", errors="replace")),
                        len(stderr_value.encode("utf-8", errors="replace")),
                    )
                    if full_output_logging and stdout_value:
                        logger.info("run stdout:\n%s", stdout_value.rstrip())
                    if stderr_value:
                        logger.warning("run stderr: %s", stderr_value.strip())
                    if full_output_logging and stderr_value:
                        logger.warning("run stderr(full):\n%s", stderr_value.rstrip())

                    _send_json(
                        conn,
                        {
                            "ok": exit_code == 0,
                            "exit_code": exit_code,
                            "stdout": stdout_value,
                            "stderr": stderr_value,
                        },
                    )
                except Exception as e:
                    logger.exception("request handling failed device_id=%r error=%s", _active_device_id(serial), e)
                    _send_json(conn, {"ok": False, "error": str(e), "exit_code": 1})
    finally:
        logger.info("daemon stopping serial=%r device_id=%r", serial, _active_device_id(serial))
        server.close()
        _remove_file(sock_file)
        _remove_file(pid_file)


def start_daemon(
    serial: Optional[str],
    timeout: float = 6.0,
    full_output_log: Optional[bool] = None,
) -> tuple[bool, str]:
    if is_running(serial):
        return True, "u2cli daemon is already running"

    cmd = [sys.executable, "-m", "u2cli.daemon", "serve"]
    if serial:
        cmd.extend(["--serial", serial])

    popen_env = os.environ.copy()
    if full_output_log is not None:
        popen_env[ENV_DAEMON_LOG_FULL_OUTPUT] = "1" if full_output_log else "0"

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=popen_env,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_running(serial):
            return True, "u2cli daemon started"
        time.sleep(0.1)

    return False, "failed to start u2cli daemon"


def stop_daemon(serial: Optional[str]) -> tuple[bool, str]:
    if not is_running(serial):
        return True, "u2cli daemon is not running"
    try:
        send_request(serial, {"action": "stop"}, timeout=2.0)
        return True, "u2cli daemon stopped"
    except Exception as e:
        return False, str(e)


def daemon_status(serial: Optional[str]) -> Dict[str, Any]:
    running = is_running(serial)
    data: Dict[str, Any] = {
        "running": running,
        "socket": socket_path(serial),
        "pid_file": pid_path(serial),
        "log_file": log_path(serial),
    }
    if running:
        try:
            resp = send_request(serial, {"action": "ping"}, timeout=1.0)
            data["pid"] = resp.get("pid")
            data["full_output_log"] = bool(resp.get("full_output_log"))
        except Exception:
            data["running"] = False
    return data


def should_delegate_command(invoked_subcommand: Optional[str]) -> bool:
    if os.getenv(ENV_IN_DAEMON) == "1":
        return False
    if not invoked_subcommand:
        return False
    if invoked_subcommand in {"daemon", "repl"}:
        return False
    return True


def run_via_daemon(serial: Optional[str], argv: list[str]) -> int:
    full_output_log = _env_true(ENV_DAEMON_LOG_FULL_OUTPUT)
    ok, msg = start_daemon(serial, full_output_log=full_output_log)
    if not ok:
        click.echo(json.dumps({"error": msg, "type": "DaemonStartError"}, ensure_ascii=False), err=True)
        return 1

    try:
        resp = send_request(serial, {"action": "run", "argv": argv}, timeout=300.0)
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False), err=True)
        return 1

    if resp.get("stdout"):
        sys.stdout.write(resp["stdout"])
    if resp.get("stderr"):
        sys.stderr.write(resp["stderr"])

    return int(resp.get("exit_code", 1))


def _parse_daemon_argv(argv: list[str]) -> tuple[str, Optional[str]]:
    action = "serve"
    serial = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in {"serve", "status", "start", "stop", "logs"}:
            action = arg
            i += 1
            continue
        if arg in {"-s", "--serial"} and i + 1 < len(argv):
            serial = argv[i + 1]
            i += 2
            continue
        i += 1
    return action, serial


def main() -> None:
    action, serial = _parse_daemon_argv(sys.argv[1:])
    if action == "serve":
        serve(serial)
        return
    if action == "status":
        click.echo(json.dumps(daemon_status(serial), ensure_ascii=False))
        return
    if action == "start":
        ok, msg = start_daemon(serial)
        click.echo(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        raise SystemExit(0 if ok else 1)
    if action == "stop":
        ok, msg = stop_daemon(serial)
        click.echo(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        raise SystemExit(0 if ok else 1)
    if action == "logs":
        click.echo(read_log_tail(serial), nl=False)
        return


if __name__ == "__main__":
    main()
