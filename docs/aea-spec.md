# `.aea` Task Script Specification

This reference defines the `.aea` task script format accepted by:

- `android-emu-agent task validate`
- `android-emu-agent task run`

`.aea` scripts are compact, line-oriented files that compile into the JSON task harness shape:
metadata, ordered steps, optional step verifiers, and optional final verifiers.

For a hands-on guide, see [Create and Run Task Scripts](tasks.md).

## File Types

The CLI parses files with these suffixes as task scripts:

| Suffix        | Meaning                                  |
| ------------- | ---------------------------------------- |
| `.aea`        | Standard task script                     |
| `.aea-task`   | Task script alias                        |
| `.aea-replay` | Task script alias for replay-style flows |

Other task files are parsed as JSON.

## Processing Model

The parser reads the file one line at a time:

1. Strip comments that begin with `#` outside quoted strings.
2. Ignore blank lines.
3. Tokenize the remaining line with shell-style quoting.
4. Lowercase the first token and treat it as the command keyword.
5. Convert the command into the JSON task spec shape.
6. Validate the compiled task shape before execution.

A script is invalid when it contains no steps and no final verifiers.

## Lexical Rules

| Rule        | Behavior                                                                             | Example                                          |
| ----------- | ------------------------------------------------------------------------------------ | ------------------------------------------------ |
| Comments    | `#` starts a comment outside single or double quotes.                                | `tap text:"Pay #1" # comment`                    |
| Quoting     | Single or double quotes preserve spaces.                                             | `description "Open checkout and verify payment"` |
| Options     | Options use `key=value` syntax.                                                      | `wait idle timeout_ms=5000`                      |
| Option keys | `-` normalizes to `_`.                                                               | `duration-ms=300` becomes `duration_ms`.         |
| Booleans    | `true` and `false` become booleans.                                                  | `wait_debugger=true`                             |
| Numbers     | Numeric coercion applies to `timeout_ms`, `duration_ms`, `duration`, and `distance`. | `distance=0.8`                                   |
| Selectors   | Selector-like tokens are values even when they contain `=`.                          | `text:"Save" enabled:true`                       |

Selector-like tokens are recognized when they start with one of these prefixes:

- `^`
- `text:`
- `id:`
- `desc:`
- `class:`
- `coords:`

## Metadata Commands

Metadata commands set top-level task fields.

| Command                | Required | Compiled field | Notes                                           |
| ---------------------- | -------- | -------------- | ----------------------------------------------- |
| `name <text>`          | No       | `name`         | Defaults to `unnamed script task` when omitted. |
| `description <text>`   | No       | `description`  | Preserved as task metadata.                     |
| `session <session_id>` | No       | `session_id`   | Used by `task run` when `--session` is omitted. |

Example:

```text
name "checkout smoke"
description "Tap checkout and verify payment UI state."
session s-abc123
```

## Step Commands

Step commands append entries to `steps`.

### App Steps

| Script form            | Compiled operation      | Required values |
| ---------------------- | ----------------------- | --------------- |
| `launch <package>`     | `{"app": "launch"}`     | `package`       |
| `force-stop <package>` | `{"app": "force_stop"}` | `package`       |
| `deeplink <uri>`       | `{"app": "deeplink"}`   | `uri`           |

Example:

```text
launch com.example.app
force-stop com.example.app
deeplink https://example.com/checkout
```

### Action Steps

| Script form                  | Compiled operation       | Required values                           |
| ---------------------------- | ------------------------ | ----------------------------------------- |
| `tap <selector>`             | `{"action": "tap"}`      | `ref` containing a ref or selector string |
| `long-tap <selector>`        | `{"action": "long_tap"}` | `ref` containing a ref or selector string |
| `clear <selector>`           | `{"action": "clear"}`    | `ref` containing a ref or selector string |
| `set-text <selector> <text>` | `{"action": "set_text"}` | `ref`, `text`                             |
| `swipe <direction>`          | `{"action": "swipe"}`    | `direction`                               |
| `back`                       | `{"action": "back"}`     | None                                      |
| `home`                       | `{"action": "home"}`     | None                                      |
| `recents`                    | `{"action": "recents"}`  | None                                      |

Example:

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

Notes:

- `tap`, `long-tap`, and `clear` join the remaining line into one selector string. This allows
  fallback and compound selectors.
- `set-text` treats the first value token as the selector and the rest of the line as text. Use a
  single selector token such as `^a2`, `id:com.example:id/email`, or `text:"Email"`.
- `swipe` supports options such as `distance=0.8` and `duration_ms=300`.

### Wait Steps

| Script form                | Compiled operation     | Required values       |
| -------------------------- | ---------------------- | --------------------- |
| `wait idle`                | `{"wait": "idle"}`     | None                  |
| `wait activity <activity>` | `{"wait": "activity"}` | `activity`            |
| `wait text <text>`         | `{"wait": "text"}`     | `text`                |
| `wait exists <selector>`   | `{"wait": "exists"}`   | `ref` selector string |
| `wait gone <selector>`     | `{"wait": "gone"}`     | `ref` selector string |

Example:

```text
wait idle timeout_ms=5000
wait activity HomeActivity timeout_ms=15000
wait text "Payment complete" timeout_ms=5000
wait exists text:"Payment" timeout_ms=5000
wait gone text:"Loading" timeout_ms=10000
```

### UI Steps

| Script form             | Compiled operation                      | Notes                         |
| ----------------------- | --------------------------------------- | ----------------------------- |
| `snapshot`              | `{"ui": "snapshot"}`                    | Uses compact mode by default. |
| `snapshot mode=compact` | `{"ui": "snapshot", "mode": "compact"}` | Compact actionable snapshot.  |
| `snapshot mode=full`    | `{"ui": "snapshot", "mode": "full"}`    | Full UI hierarchy snapshot.   |
| `snapshot mode=raw`     | `{"ui": "snapshot", "mode": "raw"}`     | Raw XML hierarchy.            |

## Verifiers

Verifiers use the same operations as wait steps: `idle`, `activity`, `text`, `exists`, and `gone`.

| Command                  | Scope               | Placement                           |
| ------------------------ | ------------------- | ----------------------------------- |
| `verify <operation> ...` | Previous step only  | Must appear after a step.           |
| `expect <operation> ...` | Final task verifier | Can appear anywhere after metadata. |

Example:

```text
tap text:"Continue" || id:com.example:id/continue
verify exists text:"Welcome" timeout_ms=5000
expect activity HomeActivity
```

A `verify` line before any step is invalid.

## Selector Values

Script selectors pass through to the same selector parser used by action, wait, and expectation
commands. Common forms:

```text
^a1
text:"Sign in"
text-contains:"Pay"
id:com.example:id/login
desc:"Open menu"
label:"Open menu"
class:android.widget.Button
coords:540,1200
text:"Sign in" || id:com.example:id/login
text:"Sign in" enabled:true clickable:true
```

Run this command when an automation planner needs to discover supported selector forms:

```bash
uv run android-emu-agent device capabilities --session <session-id> --json
```

## Compiled Shape

This script:

```text
name "login smoke"
session s-abc123
launch com.example.app
wait exists text:"Sign in" timeout_ms=5000
tap text:"Sign in" || id:com.example:id/login
verify exists text:"Email"
set-text id:com.example:id/email "agent@example.com"
expect activity MainActivity
```

Compiles to this task shape:

```json
{
  "name": "login smoke",
  "session_id": "s-abc123",
  "steps": [
    { "app": "launch", "package": "com.example.app" },
    { "wait": "exists", "ref": "text:Sign in", "timeout_ms": 5000 },
    {
      "action": "tap",
      "ref": "text:Sign in || id:com.example:id/login",
      "verify": [{ "type": "exists", "ref": "text:Email" }]
    },
    { "action": "set_text", "ref": "id:com.example:id/email", "text": "agent@example.com" }
  ],
  "verifiers": [{ "type": "activity", "activity": "MainActivity" }]
}
```

## Validation

Validate every script before running it:

```bash
uv run android-emu-agent task validate examples/tasks/checkout-smoke.aea
```

Validation checks:

- Script syntax.
- Required command arguments.
- Supported task operations.
- Compiled task shape.

Validation does not contact a device and does not confirm that selectors exist on the target screen.

## Error Codes

| Error code                  | Meaning                                                          | Recovery                                                             |
| --------------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------- |
| `ERR_TASK_SCRIPT_INVALID`   | The line-oriented parser rejected the script.                    | Fix the reported line and run `task validate` again.                 |
| `ERR_TASK_INVALID`          | The compiled JSON task shape is invalid.                         | Fix required fields such as `ref`, `text`, `package`, or `activity`. |
| `ERR_TASK_UNSUPPORTED_STEP` | The task uses an unsupported action, wait, app, or UI operation. | Use the supported command forms in this specification.               |
| `ERR_NOT_FOUND`             | A selector did not match during execution.                       | Capture a fresh snapshot and update the selector.                    |
| `ERR_TIMEOUT`               | A wait or verifier did not complete before timeout.              | Check actual state or increase `timeout_ms`.                         |
| `ERR_EXPECTATION_FAILED`    | A final expectation failed.                                      | Inspect the failure payload and collect artifacts before retrying.   |

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
