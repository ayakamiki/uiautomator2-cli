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

## 8. XPath Subset Coverage

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

## 9. Negative Checks

Example commands:

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[@text='DefinitelyNotThere']"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='DefinitelyNotThere']"
```

Pass criteria:

- [ ] `xpath-exists` returns `false` for a missing node
- [ ] `xpath-click` fails clearly for a missing node
- [ ] no unrelated element is clicked by mistake

## 10. Boundary Confirmation

This validation pass should only support these conclusions:

- [ ] Harmony `dump-hierarchy` now uses normalized hierarchy output
- [ ] Harmony `xpath-*` is re-enabled and usable
- [ ] both shorthand and full XPath forms work on Harmony

This pass should not be used to claim:

- [ ] strict panel verification for `open-notification`
- [ ] strict panel verification for `open-quick-settings`
- [ ] `app-install` / `app-uninstall` support is available

## 11. Recommended Record Template

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

## 12. Recommended Minimal Acceptance Set

For a single lightweight real-device regression pass, complete at least these 6 items:

- [ ] `u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png`
- [ ] `dump-hierarchy`
- [ ] `dump-hierarchy --raw`
- [ ] one successful `xpath-exists` case
- [ ] one successful `xpath-click` case
- [ ] one successful `xpath-set-text` case with visible UI change