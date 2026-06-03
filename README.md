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

For Harmony support:

```bash
pip install 'uiautomator2-cli[harmony]'
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

For Harmony support:
- `hdc` available in `PATH` (or via `HDC_BIN`)
- `hmdriver2` installed via the `harmony` extra

## Android vs Harmony

| Topic | Android | Harmony |
| --- | --- | --- |
| Install | `pip install uiautomator2-cli` | `pip install 'uiautomator2-cli[harmony]'` |
| Transport | ADB | HDC |
| Driver runtime | `uiautomator2` | `hmdriver2` |
| Recommended CLI flag | `--platform android` | `--platform harmony` |
| Default when omitted | `auto` resolves to Android | Must opt in explicitly |
| `--package` meaning | Native package selector | Hierarchy bundle/package filter before fallback to a concrete native selector |
| Dynamic selector path | Native `uiautomator2` selector fields | Hierarchy-assisted resolution, then fallback to a concrete native selector |

## Quick Start

```bash
# Show help
u2cli --help

# Click by text
u2cli click --text "Settings"

# Get text by resource/element ID
u2cli get-text --resource-id entry_title

# Screenshot
u2cli screenshot screen.png

# Show foreground app
u2cli current-app

# Press a common named key
u2cli press back

# Harmony real-device validated aliases: recent / menu / enter / delete /
# volume_up / volume_down / power
u2cli --platform harmony press recent

# Show active media playback info on Android or Harmony
# `u2_code` shows `dumpsys media_session` on Android and `AVSessionService` hidumper on Harmony
u2cli playback-info

# Control media playback on Android or Harmony
u2cli media-control play-pause

# Harmony also supports zero-install media control over hdc + uitest
u2cli --platform harmony media-control next

# On Harmony, `stop` is delivered but tested players may treat it like pause
u2cli --platform harmony media-control stop

# Harmony element examples: click by description regex
u2cli --platform harmony click --description-matches "Login.*button"

# Harmony element examples: get text by bundle/package + text prefix
u2cli --platform harmony get-text --package com.demo.app --text-starts-with "Welcome"

# Harmony element examples: check existence by bundle/package + text contains
u2cli --platform harmony exists --package com.demo.app --text-contains "Login"
```

## Daemon-First Design

`u2cli` routes normal commands through a background daemon.

For normal commands:
- First command auto-starts daemon
- Following commands reuse the same daemon process
- If the on-disk Python code changes, the CLI detects a stale daemon and restarts it automatically

Commands not delegated to daemon:
- `u2cli daemon ...` (daemon management)
- `u2cli repl` (interactive same-process mode)

Development controls:
- `u2cli --no-daemon ...` runs a command in-process and bypasses the background daemon
- `u2cli daemon restart` forces a fresh daemon for the current platform/serial target

## Multi-Device Isolation

Daemon instances are isolated by platform + device serial.

- `--platform <platform>` + `-s <serial>`: use the daemon instance for that exact platform/serial pair
- `--platform <platform>` without `-s`: use the default daemon instance for that platform
- Each platform/serial pair has independent socket, pid file, and log file

For mixed Android/Harmony workflows, always pass `--platform` explicitly. For multi-device workflows, also pass `-s` explicitly.

## Connection and Retry Behavior

`connect_device()` behavior:

- In daemon process: `u2.connect` retries once on failure (max 2 attempts)
- Outside daemon path: single attempt
- Per-serial device object is cached in-process and reused

## Real-Device Smoke

Use `u2cli-smoke` for a fast sanity check against a connected target.

For a deeper Harmony real-device acceptance pass covering `dump-hierarchy` and `xpath-*`, see [docs/harmony-real-device-checklist.en.md](docs/harmony-real-device-checklist.en.md).

```bash
# Android smoke with playback_info included
u2cli-smoke --platform android -s DEVICE-001 --json

# Harmony smoke with screenshot artifact
u2cli-smoke --platform harmony -s TARGET-001 --screenshot smoke.png
```

The smoke run checks device info, window size, current app, screenshot capture, hierarchy dump, and `playback-info`.
On Android, `playback-info` reads `dumpsys media_session` and is the preferred verification path for member-only media flows where paywall overlays can hide the actual playback result.
On Harmony, `playback-info` reads `AVSessionService` metadata and can still report the active background playback session even when the foreground app is not the music app.

`media-control` maps `play`, `pause`, `play-pause`, `next`, `previous`, and `stop` to platform media controls.
On Harmony, `u2cli` uses the built-in zero-install `uitest uiInput keyEvent` path over `hdc`.
On tested Harmony hardware, `play`, `pause`, `play-pause`, `next`, and `previous` changed the active AVSession as expected. `stop` was delivered too, but Huawei Music, QQ Music, and Kugou each interpreted it as a pause-style transition rather than a distinct stopped state. Treat Harmony `stop` as "dispatch guaranteed, resulting playback state player-dependent" instead of assuming a strict stopped state.

## Logging

### Log Location

Per-platform/per-serial log files under:

```bash
~/.u2cli/logs/
```

Examples:
- `u2cli-daemon-android-default.log`
- `u2cli-daemon-android-s-xxxxxxxxxx.log`
- `u2cli-daemon-harmony-default.log`
- `u2cli-daemon-harmony-s-xxxxxxxxxx.log`

### Log Rotation

`RotatingFileHandler` is enabled:
- `maxBytes = 5MB`
- `backupCount = 3`

That means current log + up to 3 rotated files per platform/serial pair.

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
export ANDROID_SERIAL=TARGET-001
export U2CLI_DAEMON_LOG_FULL_OUTPUT=1
u2cli device-info
```

## Global Options

Use before subcommand:

- `-s, --serial`: target device serial
- `--platform`: backend platform (`android`, `harmony`, `auto`)
- `--json`: JSON output
- `--version`: show version

## Selector Notes

Element commands share the same cross-platform selector surface across Android and Harmony.

- `--description-matches`: match accessibility description by regex
- `--description-starts-with`: match accessibility description by prefix
- `--package`: package/bundle filter

`--package` semantics are platform-specific:

- Android: matches the native package name selector
- Harmony: filters by hierarchy bundle/package attributes during selector resolution, then falls back to a concrete native selector for execution

Example:

```bash
u2cli --platform harmony click \
  --description-matches "Login.*button" \
  --package com.demo.app
```

## Harmony Selector Behavior

When `--platform harmony` is enabled:

- `--description-matches` and `--description-starts-with` are supported at the CLI layer
- `--text-contains`, `--text-starts-with`, `--text-matches`, `--description-matches`, `--description-starts-with`, and `--package` use hierarchy-assisted resolution before execution
- `--package` is a bundle/package filter during selector resolution, not a direct native Harmony selector field
- In mixed-platform scripts, prefer passing `--platform harmony` explicitly instead of relying on defaults

## Harmony current-app Notes

On Harmony devices, `current-app` now uses layered detection:

- Foreground app pages prefer `aa dump` foreground mission data and return `package + activity/ability`
- Home/launcher scenes fall back to the focused top-level hierarchy bundle
- On tested real devices, the home screen returns `com.ohos.sceneboard`

Examples:

```bash
u2cli --platform harmony current-app
# Home example result: {"package": "com.ohos.sceneboard", "activity": null}
```

## Harmony Support Boundary

The Harmony backend surface is intentionally narrower than the raw backend internals.

- Shared selector-based element commands such as `click`, `long-click`, `get-text`, `set-text`, `clear-text`, and `exists` are supported.
- `xpath-*` now runs through the normalized hierarchy/XPath service on Harmony instead of the earlier backend-native locator bridge.
- `dump-hierarchy` now renders from the normalized hierarchy model on Harmony. `--raw` still returns backend XML when you need the original payload.
- `open-notification` and `open-quick-settings` are currently partial best-effort gesture recipes on Harmony. `open-notification` retries with a stronger follow-up swipe when the post-gesture hierarchy still looks like the desktop, but neither command yet performs strict panel-open verification.
- `app-install` and `app-uninstall` are currently gated on Harmony until the app artifact model is normalized across Android APK and Harmony package/HAP flows.
- `app-info`, `app-list`, and `app-list-running` are currently partial compatibility views on Harmony rather than the final normalized app-service schema.

## Harmony XPath Examples

`xpath-*` commands now use the normalized hierarchy/XPath service on Harmony. They support both full XPath and the existing shorthand forms:

- `Login`: exact text / description / resource-id match
- `%Login%`: text contains
- `Welcome%`: text starts with
- `%button`: text ends with
- `^Login.*`: text regex
- `@entry_button`: exact resource/element ID shorthand

Examples:

```bash
u2cli --platform harmony xpath-click "%Login%"
u2cli --platform harmony xpath-get-text "//Button[contains(@content-desc, 'Primary')]"
u2cli --platform harmony xpath-exists "//Button[@text='Login'][2]"
```

## Command Overview

### Element Commands

Selector-based element actions shared across Android and Harmony.

- `click`
- `long-click`
- `drag-and-drop-element`
- `pinch-in`
- `pinch-out`
- `get-text`
- `set-text`
- `clear-text`
- `exists`
- `wait`
- `element-info`
- `swipe-element`
- `scroll`

`drag-and-drop-element` uses one source selector and one target selector in the same command.
Target selector options use the `--target-*` prefix, for example `--target-text`, `--target-resource-id`, and `--target-description`.
For Harmony launcher icon rearrangement scenarios, prefer coordinate dragging with `drag-and-drop FX FY TX TY`
because launcher acceptance can be gesture-timing sensitive. Start with `--duration 1.2` and then tune both
duration and destination coordinates if needed.

### XPath Commands

Locator-based element actions backed by the normalized hierarchy/XPath service.

- `xpath-click`
- `drag-and-drop-xpath`
- `xpath-exists`
- `xpath-get-text`
- `xpath-set-text`

`drag-and-drop-xpath SOURCE_LOCATOR TARGET_LOCATOR` resolves both locators through the normalized XPath service and drags the source node to the target node.

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
- `drag-and-drop`
- `zoom`
- `send-keys`
- `open-notification`
- `open-quick-settings`
- `open-url`
- `shell`
- `current-app`

`zoom --center-x --center-y --percent` uses the UI element covering the given center point.
Positive `--percent` zooms in, negative `--percent` zooms out, and `abs(percent)` must be between 1 and 100.

Harmony notes for partially exposed screen/device commands:

- `open-notification`: partial best-effort Harmony gesture recipe with desktop-state retry, but without strict panel verification.
- `open-quick-settings`: partial best-effort Harmony gesture recipe without panel verification.

`press KEY` accepts integer keycodes on every backend. For named keys, the shared documented set is
`home`, `back`, `menu`, `enter`, `delete`, `recent`, `volume_up`, `volume_down`, `power`.
On the connected Harmony test device, `home`, `back`, `recent`, `menu`, `enter`, `delete`,
`volume_up`, `volume_down`, and `power` were all validated to dispatch real device key events.
`power` produced a visible screen-off transition and wake-up recovery; `volume_up` / `volume_down`
also produced visible screen changes. `enter` / `delete` were further validated end to end in a real
Harmony Notes editor: typing `AB`, then pressing `delete`, reduced the visible body text to `A`; pressing
`enter` and typing `C` produced a second line (`A` newline `C`). `recent` and `menu` still dispatched
successfully, but their visible result remained scene-dependent on the tested launcher/settings context.

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

Harmony notes for app commands:

- `app-start`, `app-stop`, `app-clear`, and `app-wait` are part of the current shared Harmony subset.
- `app-install` and `app-uninstall` are currently gated on Harmony.
- `app-info`, `app-list`, and `app-list-running` are currently partial compatibility views on Harmony and include `partial` metadata in JSON output.

### Others

- `repl`
- `daemon start|status|logs|stop`

## Common Examples

```bash
# Click on a specific platform/serial target
u2cli -s TARGET-001 click --text "Wi-Fi"

# JSON output
u2cli --json exists --text "Settings"

# Check daemon status for the current platform/serial target
u2cli -s TARGET-001 daemon status

# Tail daemon logs for the current platform/serial target
u2cli -s TARGET-001 daemon logs --lines 200
```

## JSON Output Examples

```bash
$ u2cli --json exists --text "Settings"
{"u2_code": "d(text='Settings').exists", "result": true}

# Get text by resource/element ID
$ u2cli --json get-text --resource-id entry_title
{"u2_code": "d(resourceId='entry_title').get_text(timeout=3.0)", "result": "Welcome"}

# Android playback-info output
$ u2cli --json playback-info
{"u2_code": "d.shell('dumpsys media_session')", "result": {"source": "media_session", "package": "com.tencent.qqmusic", "state": {"code": 3, "name": "playing"}}}

# Harmony playback-info output
$ u2cli --json --platform harmony playback-info
{"u2_code": "d.shell(\"hidumper -s AVSessionService -a '-show_session_info'\")", "result": {"source": "avsession", "package": "com.huawei.hmsapp.music", "state": {"code": 2, "name": "paused"}}}
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
