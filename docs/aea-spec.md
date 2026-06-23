# `.aea` Task Script Specification

This document specifies the `.aea` task script format accepted by `android-emu-agent task validate`
and `android-emu-agent task run`.

`.aea` scripts are a compact, line-oriented representation of the JSON task harness. Each script
compiles into a task object with metadata, ordered steps, optional step verifiers, and optional
final task verifiers.

## File Types

The CLI treats files with these suffixes as task scripts:

- `.aea`
- `.aea-task`
- `.aea-replay`

Other task files are parsed as JSON.

## Processing Model

The parser reads the file one line at a time:

1. Strip comments that begin with `#` outside quoted strings.
2. Ignore blank lines.
3. Tokenize the line with shell-style quoting.
4. Dispatch on the first token as the command keyword.
5. Convert the command into the JSON task spec shape.

A script is invalid if it contains no steps and no final verifiers.

## Lexical Rules

Comments begin with `#` unless the character appears inside single or double quotes:

```text
tap text:"Pay #1" # comment
```

Quoted strings preserve spaces:

```text
description "Launch the app and verify the home screen."
set-text id:com.example:id/email "agent@example.com"
```

Options use `key=value` syntax:

```text
wait idle timeout_ms=5000
swipe down distance=0.8 duration_ms=300
```

Option keys normalize `-` to `_`. Boolean option values `true` and `false` become booleans. Numeric
coercion is applied to `timeout_ms`, `duration_ms`, `duration`, and `distance`.

Selector tokens that start with `^`, `text:`, `id:`, `desc:`, `class:`, or `coords:` are treated as
selector values even when they contain `=`.

## Command Forms

### Metadata

Metadata commands set top-level task fields:

```text
name "checkout smoke"
description "Tap checkout and verify payment UI state."
session s-abc123
```

- `name <text>` sets the task name.
- `description <text>` sets the task description.
- `session <session_id>` sets the default session used by `task run`.

If `session` is omitted, `task run` must receive `--session`.

### App Steps

```text
launch com.example.app
force-stop com.example.app
deeplink https://example.com/checkout
```

- `launch <package>` compiles to app operation `launch`.
- `force-stop <package>` compiles to app operation `force_stop`.
- `deeplink <uri>` compiles to app operation `deeplink`.

### Action Steps

```text
tap text:"Checkout" || id:com.example:id/checkout
long-tap desc:"Item menu"
clear id:com.example:id/search
set-text id:com.example:id/email "agent@example.com"
swipe down distance=0.8 duration_ms=300
back
home
recents
```

- `tap <selector>` compiles to action operation `tap`.
- `long-tap <selector>` compiles to action operation `long_tap`.
- `clear <selector>` compiles to action operation `clear`.
- `set-text <selector> <text>` compiles to action operation `set_text`.
- `swipe <direction>` compiles to action operation `swipe`.
- `back`, `home`, and `recents` compile to matching action operations.

`tap`, `long-tap`, and `clear` accept the remaining line as the selector, so fallback and compound
selectors can contain spaces. `set-text` currently treats the first value token as the selector and
the rest of the line as text, so use a single selector token such as a ref or resource ID.

### Wait Steps

```text
wait idle timeout_ms=5000
wait activity HomeActivity timeout_ms=15000
wait text "Payment complete" timeout_ms=5000
wait exists text:"Payment" timeout_ms=5000
wait gone text:"Loading" timeout_ms=10000
```

- `wait idle` waits for UI idle.
- `wait activity <activity>` waits for an activity match.
- `wait text <text>` waits for visible text.
- `wait exists <selector>` waits for an element selector to exist.
- `wait gone <selector>` waits for an element selector to disappear.

### UI Steps

```text
snapshot
snapshot mode=compact
snapshot mode=full
snapshot mode=raw
```

`snapshot` compiles to UI operation `snapshot`. If `mode` is omitted, the daemon uses compact mode.

### Verifiers

Step verifiers attach to the previous step:

```text
tap text:"Continue" || id:com.example:id/continue
verify exists text:"Welcome" timeout_ms=5000
```

Final task verifiers run after all steps:

```text
expect activity HomeActivity
```

`verify` and `expect` use the same operations as `wait`: `idle`, `activity`, `text`, `exists`, and
`gone`. A `verify` line before any step is invalid.

## Selector Values

Script selectors are passed through to the same selector parser used by action, wait, and
expectation commands. Common forms include:

- `^a1`
- `text:"Sign in"`
- `text-contains:"Pay"`
- `id:com.example:id/login`
- `desc:"Open menu"`
- `label:"Open menu"`
- `class:android.widget.Button`
- `coords:540,1200`
- `text:"Sign in" || id:com.example:id/login`
- `text:"Sign in" enabled:true clickable:true`

Run `device capabilities` for the active target when an automation planner needs to discover which
selector forms are supported.

## Validation

Always validate scripts before running them:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
```

Validation checks syntax, required arguments, supported commands, and the compiled task shape. It
does not contact a device or prove that selectors exist on the target app.

## Minimal Example

```text
name "idle snapshot"
wait idle timeout_ms=5000
snapshot mode=compact
```

## App Flow Example

```text
name "login flow smoke"
launch com.example.app
wait idle timeout_ms=10000
tap text:"Sign in" || id:com.example:id/sign_in
verify exists text:"Email" timeout_ms=5000
set-text id:com.example:id/email "agent@example.com"
set-text id:com.example:id/password "test-password"
tap text:"Continue" || id:com.example:id/continue
expect activity HomeActivity
```
