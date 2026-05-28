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
from pathlib import Path
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

from u2cli.backends.factory import resolve_platform


ENV_IN_DAEMON = "U2CLI_IN_DAEMON"
ENV_DAEMON_LOG_FILE = "U2CLI_DAEMON_LOG_FILE"
ENV_DAEMON_LOG_FULL_OUTPUT = "U2CLI_DAEMON_LOG_FULL_OUTPUT"
_DEFAULT_DEVICE_MISSING_PATTERNS = (
    re.compile(r"device\s+'.+?'\s+not\s+found", re.IGNORECASE),
    re.compile(r"device\s+.+?\s+not\s+found", re.IGNORECASE),
    re.compile(r"no\s+device", re.IGNORECASE),
    re.compile(r"transport.*not\s+found", re.IGNORECASE),
)
_HARMONY_TRANSPORT_ERROR_PATTERNS = (
    re.compile(r"no\s+devices\s+found", re.IGNORECASE),
    re.compile(r"device\s*\[.+?\]\s+not\s+found", re.IGNORECASE),
    re.compile(r"please\s+connect\s+a\s+device", re.IGNORECASE),
    re.compile(r"hdc\s+.*error", re.IGNORECASE),
    re.compile(r"failed\s+to\s+list\s+hdc\s+targets", re.IGNORECASE),
    re.compile(r"broken\s+pipe", re.IGNORECASE),
    re.compile(r"connection\s+reset", re.IGNORECASE),
    re.compile(r"timed?\s*out", re.IGNORECASE),
)
_HARMONY_TRANSPORT_ERROR_TYPES = {
    "DeviceNotFoundError",
    "HdcError",
    "HmDriverError",
    "TimeoutError",
    "ConnectionResetError",
    "BrokenPipeError",
    "ConnectionRefusedError",
    "OSError",
}


def current_code_fingerprint() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha1()

    for path in sorted(root.rglob("*.py")):
        stat = path.stat()
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))

    return digest.hexdigest()[:12]


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _serial_token(serial: Optional[str]) -> str:
    if not serial:
        return "default"
    digest = hashlib.sha1(serial.encode("utf-8")).hexdigest()[:10]
    return f"s-{digest}"


def _platform_token(platform: Optional[str]) -> str:
    return resolve_platform(platform)


def socket_path(serial: Optional[str], platform: Optional[str] = None) -> str:
    return os.path.join(tempfile.gettempdir(), f"u2cli-daemon-{_platform_token(platform)}-{_serial_token(serial)}.sock")


def pid_path(serial: Optional[str], platform: Optional[str] = None) -> str:
    return os.path.join(tempfile.gettempdir(), f"u2cli-daemon-{_platform_token(platform)}-{_serial_token(serial)}.pid")


def log_dir() -> str:
    path = os.path.join(os.path.expanduser("~"), ".u2cli", "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_path(serial: Optional[str], platform: Optional[str] = None) -> str:
    return os.path.join(log_dir(), f"u2cli-daemon-{_platform_token(platform)}-{_serial_token(serial)}.log")


def _daemon_logger(serial: Optional[str], platform: Optional[str] = None) -> logging.Logger:
    logger_name = f"u2cli.daemon.{_platform_token(platform)}.{_serial_token(serial)}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_path(serial, platform=platform),
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


def read_log_tail(serial: Optional[str], lines: int = 200, platform: Optional[str] = None) -> str:
    path = log_path(serial, platform=platform)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    if lines <= 0:
        return ""
    return "".join(content[-lines:])


def _active_device_id(serial: Optional[str], platform: Optional[str] = None) -> Optional[str]:
    if serial is not None:
        return serial

    from u2cli.device import default_device_serial
    from u2cli.transports.hdc import resolve_default_target

    resolved_platform = resolve_platform(platform)
    if resolved_platform == "harmony":
        try:
            return resolve_default_target()
        except Exception:
            return None
    return default_device_serial(platform=platform)


def _daemon_runtime_snapshot(
    serial: Optional[str],
    *,
    platform: Optional[str],
    full_output_log: bool,
    code_fingerprint: str,
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    from u2cli.device import has_cached_backend

    return {
        "ok": True,
        "pid": os.getpid(),
        "full_output_log": full_output_log,
        "code_fingerprint": code_fingerprint,
        "started_at": runtime_state["started_at"],
        "last_request_at": runtime_state.get("last_request_at"),
        "request_count": runtime_state["request_count"],
        "backend_cached": has_cached_backend(serial, platform=platform),
        "active_device_id": _active_device_id(serial, platform=platform),
    }


def _run_cli_once(
    serial: Optional[str],
    argv: list[str],
    platform: Optional[str] = None,
) -> tuple[int, str, str, Optional[BaseException]]:
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
                obj={"serial": serial, "platform": resolve_platform(platform), "output_json": False},
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


def _extract_error_details(error: Optional[BaseException], stderr_value: str) -> tuple[str | None, str]:
    message = str(error or "")
    error_type = type(error).__name__ if error is not None else None

    for line in reversed(stderr_value.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            error_type = str(payload.get("type") or error_type)
            message = str(payload.get("error") or message)
            break

    text = "\n".join(part for part in [message, stderr_value] if part)
    return error_type, text


def _looks_like_harmony_transport_error(error: Optional[BaseException], stderr_value: str) -> bool:
    error_type, text = _extract_error_details(error, stderr_value)
    if error_type in _HARMONY_TRANSPORT_ERROR_TYPES:
        return True
    lowered = text.lower()
    return any(pattern.search(lowered) for pattern in _HARMONY_TRANSPORT_ERROR_PATTERNS)


def _run_cli_with_default_retry(
    serial: Optional[str],
    argv: list[str],
    logger: logging.Logger,
    platform: Optional[str] = None,
) -> tuple[int, str, str]:
    from u2cli.device import clear_cached_device, default_device_serial, has_cached_backend

    bound_default_serial = default_device_serial(platform=platform) if serial is None else None
    exit_code, stdout_value, stderr_value, run_error = _run_cli_once(serial, argv, platform=platform)

    if (
        serial is None
        and bound_default_serial
        and exit_code != 0
        and _looks_like_missing_default_device(run_error, stderr_value, bound_default_serial)
    ):
        logger.info("default device missing, clear sticky binding and retry once device_id=%r", bound_default_serial)
        if platform is None:
            clear_cached_device()
        else:
            clear_cached_device(platform=platform)
        exit_code, stdout_value, stderr_value, run_error = _run_cli_once(serial, argv, platform=platform)

    resolved_platform = resolve_platform(platform)
    if (
        resolved_platform == "harmony"
        and exit_code != 0
        and has_cached_backend(serial, platform=resolved_platform)
        and _looks_like_harmony_transport_error(run_error, stderr_value)
    ):
        logger.info(
            "harmony transport failure detected, clear cached backend and retry once device_id=%r",
            _active_device_id(serial, platform=resolved_platform),
        )
        clear_cached_device(serial, platform=resolved_platform)
        exit_code, stdout_value, stderr_value, _ = _run_cli_once(serial, argv, platform=resolved_platform)

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


def send_request(
    serial: Optional[str],
    payload: Dict[str, Any],
    timeout: float = 30.0,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    sock_file = socket_path(serial, platform=platform)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(sock_file)
        _send_json(client, payload)
        return _recv_json(client)


def is_running(serial: Optional[str], platform: Optional[str] = None) -> bool:
    sock_file = socket_path(serial, platform=platform)
    if not os.path.exists(sock_file):
        return False
    try:
        resp = send_request(serial, {"action": "ping"}, timeout=1.0, platform=platform)
        return bool(resp.get("ok"))
    except Exception:
        return False


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def serve(serial: Optional[str], platform: Optional[str] = None) -> None:
    resolved_platform = resolve_platform(platform)
    sock_file = socket_path(serial, platform=resolved_platform)
    pid_file = pid_path(serial, platform=resolved_platform)
    logger = _daemon_logger(serial, platform=resolved_platform)
    code_fingerprint = current_code_fingerprint()
    os.environ[ENV_DAEMON_LOG_FILE] = log_path(serial, platform=resolved_platform)
    full_output_logging = _env_true(ENV_DAEMON_LOG_FULL_OUTPUT)

    _remove_file(sock_file)
    os.environ[ENV_IN_DAEMON] = "1"

    stop_flag = {"stop": False}
    runtime_state: Dict[str, Any] = {
        "started_at": int(time.time()),
        "last_request_at": None,
        "request_count": 0,
    }

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
            "daemon started serial=%r device_id=%r socket=%s pid_file=%s full_output_logging=%s code_fingerprint=%s",
            serial,
            _active_device_id(serial, platform=resolved_platform),
            sock_file,
            pid_file,
            full_output_logging,
            code_fingerprint,
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
                    logger.info("request action=%s device_id=%r", action, _active_device_id(serial, platform=resolved_platform))
                    if action == "ping":
                        _send_json(
                            conn,
                            _daemon_runtime_snapshot(
                                serial,
                                platform=resolved_platform,
                                full_output_log=full_output_logging,
                                code_fingerprint=code_fingerprint,
                                runtime_state=runtime_state,
                            ),
                        )
                        continue
                    runtime_state["last_request_at"] = int(time.time())
                    if action == "stop":
                        logger.info("request stop received device_id=%r", _active_device_id(serial, platform=resolved_platform))
                        _send_json(conn, {"ok": True})
                        stop_flag["stop"] = True
                        continue
                    if action != "run":
                        logger.warning("unknown action=%r device_id=%r", action, _active_device_id(serial, platform=resolved_platform))
                        _send_json(conn, {"ok": False, "error": "unknown action", "exit_code": 1})
                        continue

                    argv = req.get("argv") or []
                    runtime_state["request_count"] += 1
                    logger.info(
                        "run start device_id=%r argv=%s",
                        _active_device_id(serial, platform=resolved_platform),
                        json.dumps(argv, ensure_ascii=False),
                    )
                    started_at = time.time()
                    request_platform = req.get("platform")
                    exit_code, stdout_value, stderr_value = _run_cli_with_default_retry(
                        serial,
                        argv,
                        logger,
                        platform=request_platform,
                    )
                    duration_ms = int((time.time() - started_at) * 1000)
                    logger.info(
                        "run end device_id=%r exit_code=%s duration_ms=%s stdout_bytes=%s stderr_bytes=%s",
                        _active_device_id(serial, platform=resolved_platform),
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
                    logger.exception(
                        "request handling failed device_id=%r error=%s",
                        _active_device_id(serial, platform=resolved_platform),
                        e,
                    )
                    _send_json(conn, {"ok": False, "error": str(e), "exit_code": 1})
    finally:
        logger.info(
            "daemon stopping serial=%r device_id=%r",
            serial,
            _active_device_id(serial, platform=resolved_platform),
        )
        server.close()
        _remove_file(sock_file)
        _remove_file(pid_file)


def start_daemon(
    serial: Optional[str],
    platform: Optional[str] = None,
    timeout: float = 6.0,
    full_output_log: Optional[bool] = None,
) -> tuple[bool, str]:
    resolved_platform = resolve_platform(platform)
    expected_fingerprint = current_code_fingerprint()
    status = daemon_status(serial, platform=resolved_platform)
    if status.get("running"):
        current_fingerprint = status.get("code_fingerprint")
        if current_fingerprint == expected_fingerprint:
            return True, "u2cli daemon is already running"

        ok, message = stop_daemon(serial, platform=resolved_platform)
        if not ok:
            return False, f"failed to restart stale u2cli daemon: {message}"

        deadline = time.time() + timeout
        while time.time() < deadline:
            if not is_running(serial, platform=resolved_platform):
                break
            time.sleep(0.1)
        else:
            return False, "failed to stop stale u2cli daemon"

    cmd = [sys.executable, "-m", "u2cli.daemon", "serve"]
    if serial:
        cmd.extend(["--serial", serial])
    if resolved_platform:
        cmd.extend(["--platform", resolved_platform])

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
        if is_running(serial, platform=resolved_platform):
            return True, "u2cli daemon started"
        time.sleep(0.1)

    return False, "failed to start u2cli daemon"


def stop_daemon(serial: Optional[str], platform: Optional[str] = None) -> tuple[bool, str]:
    resolved_platform = resolve_platform(platform)
    if not is_running(serial, platform=resolved_platform):
        return True, "u2cli daemon is not running"
    try:
        send_request(
            serial,
            {"action": "stop", "platform": resolved_platform},
            timeout=2.0,
            platform=resolved_platform,
        )
        return True, "u2cli daemon stopped"
    except Exception as e:
        return False, str(e)


def restart_daemon(
    serial: Optional[str],
    platform: Optional[str] = None,
    timeout: float = 6.0,
    full_output_log: Optional[bool] = None,
) -> tuple[bool, str]:
    resolved_platform = resolve_platform(platform)
    ok, message = stop_daemon(serial, platform=resolved_platform)
    if not ok:
        return False, message
    return start_daemon(
        serial,
        platform=resolved_platform,
        timeout=timeout,
        full_output_log=full_output_log,
    )


def daemon_status(serial: Optional[str], platform: Optional[str] = None) -> Dict[str, Any]:
    resolved_platform = resolve_platform(platform)
    running = is_running(serial, platform=resolved_platform)
    data: Dict[str, Any] = {
        "running": running,
        "socket": socket_path(serial, platform=resolved_platform),
        "pid_file": pid_path(serial, platform=resolved_platform),
        "log_file": log_path(serial, platform=resolved_platform),
        "platform": resolved_platform,
    }
    if running:
        try:
            resp = send_request(
                serial,
                {"action": "ping", "platform": resolved_platform},
                timeout=1.0,
                platform=resolved_platform,
            )
            data["pid"] = resp.get("pid")
            data["full_output_log"] = bool(resp.get("full_output_log"))
            data["code_fingerprint"] = resp.get("code_fingerprint")
            data["started_at"] = resp.get("started_at")
            data["last_request_at"] = resp.get("last_request_at")
            data["request_count"] = resp.get("request_count")
            data["backend_cached"] = bool(resp.get("backend_cached"))
            data["active_device_id"] = resp.get("active_device_id")
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


def run_via_daemon(serial: Optional[str], platform: Optional[str], argv: list[str]) -> int:
    full_output_log = _env_true(ENV_DAEMON_LOG_FULL_OUTPUT)
    resolved_platform = resolve_platform(platform)
    ok, msg = start_daemon(serial, platform=resolved_platform, full_output_log=full_output_log)
    if not ok:
        click.echo(json.dumps({"error": msg, "type": "DaemonStartError"}, ensure_ascii=False), err=True)
        return 1

    try:
        resp = send_request(
            serial,
            {"action": "run", "argv": argv, "platform": resolved_platform},
            timeout=300.0,
            platform=resolved_platform,
        )
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False), err=True)
        return 1

    if resp.get("stdout"):
        sys.stdout.write(resp["stdout"])
    if resp.get("stderr"):
        sys.stderr.write(resp["stderr"])

    return int(resp.get("exit_code", 1))


def _parse_daemon_argv(argv: list[str]) -> tuple[str, Optional[str], Optional[str]]:
    action = "serve"
    serial = None
    platform = None

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
        if arg == "--platform" and i + 1 < len(argv):
            platform = argv[i + 1]
            i += 2
            continue
        i += 1
    return action, serial, platform


def main() -> None:
    action, serial, platform = _parse_daemon_argv(sys.argv[1:])
    if action == "serve":
        serve(serial, platform=platform)
        return
    if action == "status":
        click.echo(json.dumps(daemon_status(serial, platform=platform), ensure_ascii=False))
        return
    if action == "start":
        ok, msg = start_daemon(serial, platform=platform)
        click.echo(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        raise SystemExit(0 if ok else 1)
    if action == "stop":
        ok, msg = stop_daemon(serial, platform=platform)
        click.echo(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        raise SystemExit(0 if ok else 1)
    if action == "logs":
        click.echo(read_log_tail(serial, platform=platform), nl=False)
        return


if __name__ == "__main__":
    main()
