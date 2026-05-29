# Harmony Real-Device Validation Checklist

Chinese version: [docs/harmony-real-device-checklist.md](docs/harmony-real-device-checklist.md)

Use this checklist to validate the currently exposed Harmony backend surface, with emphasis on the newly added or changed `dump-hierarchy` and `xpath-*` flows.

Scope:

- Harmony real devices
- Local-source execution of `uiautomator2-cli`
- Real-device validation of the normalized hierarchy / XPath service

Out of scope for this pass:

- `app-install`
- `app-uninstall`
- strict panel-open verification for `open-notification`
- strict panel-open verification for `open-quick-settings`

## 1. Prerequisites

- [ ] `hdc list targets` shows the target device serial
- [ ] Harmony dependencies are installed in the current environment: `pip install -e '.[harmony]'`
- [ ] Prefer `--no-daemon` to avoid stale daemon code paths
- [ ] If you do not use `--no-daemon`, run `u2cli --platform harmony -s <SERIAL> daemon restart` first

Connection stability notes:

- [ ] During targeted debugging or immediately after code changes, prefer `--no-daemon` so the run does not reuse stale backend or Python code paths
- [ ] Once you move into high-frequency real-device debugging, especially when chaining many Harmony commands or repeatedly operating system UI surfaces such as `open-notification` or `open-quick-settings`, consider running `u2cli --platform harmony -s <SERIAL> daemon restart` once and switching back to daemon mode so each command does not rebuild the HDC / UITest channel
- [ ] After a system UI gesture or click, do not immediately chain multiple new commands; allow a short recovery window for the HDC / UITest channel before taking screenshots, dumping hierarchy, or issuing the next command

### Mode Selection Guidance

The difference between `--no-daemon` and daemon mode is not command semantics but execution path:

- `--no-daemon`: the command runs directly in the current Python process, so it is better at exposing fresh bootstrap issues such as `UITest` session rebuilds, `hmdriver2` initialization, and `HDC fport` setup problems
- daemon mode: the CLI forwards the command to a background warm process, which can reuse an existing backend and is usually closer to day-to-day high-frequency usage

Recommended decision rules:

- [ ] When debugging code or right after changing transport / backend / XPath / hierarchy code, prefer `--no-daemon` so you know the command is executing the current on-disk code
- [ ] For high-frequency real-device operations, long command chains, repeated system-UI actions, or repeated command execution, prefer daemon mode so each command does not rebuild the Harmony `UITest` session from scratch
- [ ] If you plan to use daemon mode after code changes, run `u2cli --platform harmony -s <SERIAL> daemon restart` first so the background process does not keep stale code or a dirty backend state
- [ ] If you suspect the bug is in the transport / bootstrap layer rather than in the business command itself, switch back to `--no-daemon`; it usually gives more diagnostic signal

Current real-device evidence:

- [ ] In `--no-daemon` mode, the “notification-shade media control + `playback-info`” chain has already passed a `10/10` round real-device stability stress run
- [ ] In daemon mode, the same chain also passed a `10/10` round real-device stability stress run after `daemon restart`

Recommended environment notes:

- [ ] device model
- [ ] HarmonyOS version
- [ ] target app / page name
- [ ] device serial

## 2. Basic Connectivity Check

Run:

```bash
hdc list targets
u2cli --platform harmony --no-daemon -s <SERIAL> device-info
u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png
```

Pass criteria:

- [ ] `device-info` returns successfully
- [ ] `u2cli-smoke` returns successfully
- [ ] screenshot artifact `smoke.png` is created

## 3. `dump-hierarchy` Validation

Choose a page with clear text, buttons, or an input field on screen.

Run:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy --raw
```

Pass criteria:

- [ ] default output is a tree-style text view, not raw XML
- [ ] `--raw` returns backend raw XML
- [ ] key nodes can be matched between the default output and the raw XML
- [ ] the default output reflects the main visible control hierarchy on the page

Suggested artifacts:

- [ ] save default output
- [ ] save `--raw` output
- [ ] save a matching screenshot when needed

## 4. `xpath-exists` Validation

Start from a stable element found in `dump-hierarchy`. Prefer:

- visible text
- `content-desc`
- `resource-id`

Example commands:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[contains(@content-desc, 'Primary')]"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//*[@resource-id='entry.login.primary']"
```

Pass criteria:

- [ ] at least one shorthand locator succeeds
- [ ] at least one full XPath locator succeeds
- [ ] no Harmony XPath gating error appears anymore

## 5. `xpath-get-text` Validation

Example commands:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//Button[contains(@content-desc, 'Primary')]"
```

Pass criteria:

- [ ] returned text matches what is visibly shown on screen
- [ ] both shorthand and full XPath succeed at least once

## 6. `xpath-click` Validation

Choose a control with a clear visual result after tapping it, such as:

- a button that navigates to another page
- a control that expands a panel
- a control that opens a dialog

Example commands:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='Login'][2]"
```

Pass criteria:

- [ ] the correct target is clicked
- [ ] the expected page change happens
- [ ] there is no false positive where the command succeeds but the UI stays unchanged

Suggested artifacts:

- [ ] screenshot before click
- [ ] screenshot after click
- [ ] if `[2]` is used, note the count of sibling elements and the intended position

## 7. `xpath-set-text` Validation

Choose a page with an input field whose value change is visually obvious, for example:

- notes editor
- login input
- search box

Run:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "<INPUT_XPATH>" "copilot-xpath-123"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-set-text.png
```

Pass criteria:

- [ ] the input visibly changes to `copilot-xpath-123`
- [ ] the command does not drift to the wrong control
- [ ] a follow-up `dump-hierarchy` shows the changed text when applicable

If the page uses a generic Harmony `TextInput`, add the overwrite-semantics regression below. This avoids validating only the first write while missing the more important case where the second write leaves stale text behind.

Recommended page types:

- Kugou or another music-app search field
- a login page single-line input
- any non-`RichEditor` `TextInput`

Run:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" "TEXTINPUT_REPLACED_OK"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-replaced-ok.png
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" "ZX9"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-replaced-zx9.png
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" ""
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-restored-empty.png
```

Additional pass criteria:

- [ ] after the first write, the field visibly becomes `TEXTINPUT_REPLACED_OK`
- [ ] after the second write to `ZX9`, the previous text is fully replaced rather than left behind as a concatenated value
- [ ] after writing an empty string, the field is visibly restored to empty rather than keeping stale content
- [ ] all three `xpath-get-text` results match the visible UI state

Suggested artifacts:

- [ ] `textinput-replaced-ok.png`
- [ ] `textinput-replaced-zx9.png`
- [ ] `textinput-restored-empty.png`

## 8. Visible `press delete / enter` Validation

This case validates that the named Harmony keys `delete` and `enter` are not only dispatched successfully, but also produce visible results in a real text-entry workflow.

Recommended page types:

- Harmony Notes editor
- any plain multi-line text field

Preconditions:

- [ ] input focus is clearly inside the body text field
- [ ] the current page does not intercept `enter` as a send or submit action

Run:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> send-keys --no-clear "AB"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot before-delete.png
u2cli --platform harmony --no-daemon -s <SERIAL> press delete
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-delete.png
u2cli --platform harmony --no-daemon -s <SERIAL> press enter
u2cli --platform harmony --no-daemon -s <SERIAL> send-keys --no-clear "C"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-enter.png
```

Pass criteria:

- [ ] after typing `AB`, the body visibly shows `AB`
- [ ] after `press delete`, the body visibly changes from `AB` to `A`
- [ ] after `press enter` and then typing `C`, the body becomes two lines: `A` on the first line and `C` on the second line
- [ ] the result is verifiable from the screen itself, without relying on logs or toast messages

Suggested artifacts:

- [ ] `before-delete.png`
- [ ] `after-delete.png`
- [ ] `after-enter.png`
- [ ] optional before/after `dump-hierarchy` output if the input field is represented clearly enough

Troubleshooting hints:

- if `enter` triggers send/search/submit, switch to a plain body text field
- if `delete` shows no visible change, verify that focus is at the end of the text and the keyboard is not intercepting the key

## 9. XPath Subset Coverage

Try to cover at least one case for each of the following:

- [ ] exact text: `Login`
- [ ] contains text: `%Login%`
- [ ] prefix text: `Welcome%`
- [ ] suffix text: `%button`
- [ ] regex: `^Login.*`
- [ ] resource-id shorthand: `@entry_button`
- [ ] `contains(...)` predicate: `//Button[contains(@content-desc, 'Primary')]`
- [ ] positional index: `//Button[@text='Login'][2]`

Pass criteria:

- [ ] at least three different shorthand forms are validated
- [ ] full XPath covers both predicate and positional index use cases

## 10. Negative Checks

Example commands:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[@text='DefinitelyNotThere']"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='DefinitelyNotThere']"
```

Pass criteria:

- [ ] `xpath-exists` returns `false` for a missing node
- [ ] `xpath-click` fails clearly for a missing node
- [ ] no unrelated element is clicked by mistake

## 11. Boundary Confirmation

This validation pass should only support these conclusions:

- [ ] Harmony `dump-hierarchy` now uses normalized hierarchy output
- [ ] Harmony `xpath-*` is re-enabled and usable
- [ ] both shorthand and full XPath forms work on Harmony

This pass should not be used to claim:

- [ ] strict panel verification for `open-notification`
- [ ] strict panel verification for `open-quick-settings`
- [ ] `app-install` / `app-uninstall` support is available

## 12. Recommended Record Template

Record at least the following fields for each case:

- [ ] test date
- [ ] tester
- [ ] device model / OS version
- [ ] page name
- [ ] command
- [ ] XPath expression
- [ ] actual result
- [ ] pass / fail
- [ ] screenshot path
- [ ] hierarchy output path

Template:

```text
Date:
Tester:
Device:
OS Version:
Page:
Command:
XPath:
Result:
Pass/Fail:
Screenshot:
Hierarchy Output:
Notes:
```

## 13. Recommended Minimal Acceptance Set

For a single lightweight real-device regression pass, complete at least these 6 items:

- [ ] `u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png`
- [ ] `dump-hierarchy`
- [ ] `dump-hierarchy --raw`
- [ ] one successful `xpath-exists` case
- [ ] one successful `xpath-click` case
- [ ] one successful `xpath-set-text` case with visible UI change

If this pass also needs to cover visible key-alias behavior, additionally complete:

- [ ] `press delete` visibly changes the body from `AB` to `A`
- [ ] `press enter` followed by typing creates a visible second line

If this pass also needs to cover real overwrite semantics for generic Harmony inputs, additionally complete:

- [ ] run `xpath-set-text` twice against `//TextInput`, and confirm the second write fully replaces the first value
- [ ] run `xpath-set-text ''` against `//TextInput`, and confirm the field is visibly restored to empty

## 14. Verified Session-Rebuild Stability Evidence

The following result is a real-device evidence sample showing that continuous Harmony `UITest` session rebuilds have passed one concrete stress case in the current code state. It is not a blanket exemption from rerunning validation; rerun after transport changes, `hmdriver2` upgrades, HarmonyOS changes, or device changes.

Verified sample A:

- Date: `2026-05-30`
- Device serial: `4VF0225708007870`
- Execution mode: `--platform harmony --no-daemon`
- Stress rounds: `10`

Per-round sequence:

- `open-notification`
- click the notification-shade media play/pause button once
- click the same button again
- swipe up to dismiss the notification shade
- run `playback-info`

Sample A observed result:

- [x] all `10/10` rounds passed
- [x] every round completed the full chain: open shade -> play/pause toggle -> second toggle -> dismiss shade -> `playback-info`
- [x] logs did not contain these error markers: `No devices found`, `HDC forward port error`, `communication channel is being established`, `JSONDecodeError`, `did not reappear via hdc`, `ruler is not exist`

Verified sample B:

- Date: `2026-05-30`
- Device serial: `4VF0225708007870`
- Execution mode: `--platform harmony` (daemon mode, with `daemon restart` executed before the stress run)
- Stress rounds: `10`

Per-round sequence:

- `open-notification`
- click the notification-shade media play/pause button once
- click the same button again
- swipe up to dismiss the notification shade
- run `playback-info`

Sample B observed result:

- [x] all `10/10` rounds passed
- [x] every round completed the full chain: open shade -> play/pause toggle -> second toggle -> dismiss shade -> `playback-info`
- [x] `daemon restart` returned successfully
- [x] logs did not contain these error markers: `No devices found`, `HDC forward port error`, `communication channel is being established`, `JSONDecodeError`, `did not reappear via hdc`, `ruler is not exist`

Conclusion boundary:

- These two evidence samples support the claim that, for the current code version, the notification-shade media-control flow plus follow-up `playback-info` survived a 10-round real-device session-rebuild stress run in both `--no-daemon` and daemon modes
- It does not automatically imply the same result for other system-UI flows, other command chains, other devices, or other HarmonyOS versions