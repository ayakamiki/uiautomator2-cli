# uiautomator2-cli

English | [中文文档](README_ZH.md)

`u2cli` is a command-line wrapper around [uiautomator2](https://github.com/openatx/uiautomator2).

Goals:
- Operate Android devices directly from CLI
- Print equivalent `uiautomator2` Python code (`u2_code`) for each command
- Reuse connections through a daemon process to avoid reconnect overhead per command

## Installation

```bash
pip install uiautomator2-cli
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv tool install uiautomator2-cli
```

For development:

```bash
uv sync --all-groups
```

## Requirements

- Python >= 3.8
- An Android device connected through ADB (USB or network)

## Quick Start

```bash
# Show help
u2cli --help

# Click by text
u2cli click --text "Settings"

# Get text by resource-id
u2cli get-text --resource-id com.android.settings:id/title

# Screenshot
u2cli screenshot screen.png

# Show foreground app
u2cli current-app
```

## Daemon-First Design

`u2cli` routes normal commands through a background daemon.

For normal commands:
- First command auto-starts daemon
- Following commands reuse the same daemon process

Commands not delegated to daemon:
- `u2cli daemon ...` (daemon management)
- `u2cli repl` (interactive same-process mode)

## Multi-Device Isolation

Daemon instances are isolated by device serial.

- `-s <serial>`: use the daemon instance for that serial
- No `-s`: use the default daemon instance
- Each serial has independent socket, pid file, and log file

For multi-device workflows, always pass `-s` explicitly.

## Connection and Retry Behavior

`connect_device()` behavior:

- In daemon process: `u2.connect` retries once on failure (max 2 attempts)
- Outside daemon path: single attempt
- Per-serial device object is cached in-process and reused

## Logging

### Log Location

Per-serial log files under:

```bash
~/.u2cli/logs/
```

Examples:
- `u2cli-daemon-default.log`
- `u2cli-daemon-s-xxxxxxxxxx.log`

### Log Rotation

`RotatingFileHandler` is enabled:
- `maxBytes = 5MB`
- `backupCount = 3`

That means current log + up to 3 rotated files per serial.

### Log Content

Default logs include:
- daemon start/stop
- request type (`ping/run/stop`)
- command argv
- duration
- exit code
- stdout/stderr byte sizes
- exceptions and tracebacks
- connect attempt and retry records

Optional full output logging includes:
- full run stdout
- full run stderr (`run stderr(full)`)

## Daemon Commands

```bash
# Start daemon (usually optional, auto-start is enabled)
u2cli daemon start

# Start daemon with full stdout/stderr logging
u2cli daemon start --full-output-log

# Show status
u2cli daemon status

# Show latest log lines
u2cli daemon logs --lines 300

# Stop daemon
u2cli daemon stop
```

`daemon status` shows:
- `running`
- `socket`
- `pid_file`
- `log_file`
- `full_output_log`
- `pid` (when running)

## Environment Variables

- `ANDROID_SERIAL`
  - Default target serial (equivalent to global `-s`)

- `U2CLI_DAEMON_LOG_FULL_OUTPUT=1`
  - Enable full stdout/stderr logging when daemon is auto-started by normal commands

Example:

```bash
export ANDROID_SERIAL=emulator-5554
export U2CLI_DAEMON_LOG_FULL_OUTPUT=1
u2cli device-info
```

## Global Options

Use before subcommand:

- `-s, --serial`: target device serial
- `--json`: JSON output
- `--version`: show version

## Command Overview

### Element Commands

- `click`
- `long-click`
- `get-text`
- `set-text`
- `clear-text`
- `exists`
- `wait`
- `element-info`
- `swipe-element`
- `scroll`

### XPath Commands

- `xpath-click`
- `xpath-exists`
- `xpath-get-text`
- `xpath-set-text`

### Device/Screen Commands

- `screenshot`
- `dump-hierarchy`
- `device-info`
- `ui-info`
- `window-size`
- `screen-on`
- `screen-off`
- `orientation`
- `press`
- `swipe`
- `swipe-ext`
- `click-coord`
- `double-click`
- `long-click-coord`
- `send-keys`
- `open-notification`
- `open-quick-settings`
- `open-url`
- `shell`
- `current-app`

### App Commands

- `app-start`
- `app-stop`
- `app-clear`
- `app-install`
- `app-uninstall`
- `app-info`
- `app-list`
- `app-list-running`
- `app-wait`

### Others

- `repl`
- `daemon start|status|logs|stop`

## Common Examples

```bash
# Click on specific device
u2cli -s emulator-5554 click --text "Wi-Fi"

# JSON output
u2cli --json exists --text "Settings"

# Check daemon status for a device
u2cli -s emulator-5554 daemon status

# Tail daemon logs for a device
u2cli -s emulator-5554 daemon logs --lines 200
```

## JSON Output Examples

```bash
$ u2cli --json exists --text "Settings"
{"u2_code": "d(text='Settings').exists", "result": true}

$ u2cli --json get-text --resource-id com.android.settings:id/title
{"u2_code": "d(resourceId='com.android.settings:id/title').get_text(timeout=3.0)", "result": "Settings"}
```

## Troubleshooting

- If a command fails, check:
  - `u2cli daemon status`
  - `u2cli daemon logs --lines 300`

- If one serial has connection issues:
  1. `u2cli -s <serial> daemon stop`
  2. `u2cli -s <serial> daemon start`
  3. Retry your command

- For multi-device execution, always use `-s`.

## License

MIT
