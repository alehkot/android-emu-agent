# Command Reference

> **Read this file when** you need to look up a command, its arguments, or selector syntax.

Commands below call `android-emu-agent` directly. Inside an android-emu-agent source checkout,
prefix every command with `uv run` (see SKILL.md, Core Rules).

This file is a task-planning cheat sheet, not the exhaustive CLI source of truth. For current full
help, use `android-emu-agent --help` and subcommand help, or the generated reference at
<https://alehkot.github.io/android-emu-agent/reference/>.

Most commands accept `--json` for machine-readable JSON output (useful for scripting or when you
need to parse structured results programmatically).

JSON responses also include `diagnostic_id`, and the same value is returned in the `x-diagnostic-id`
header for request-level tracing.

Emulator lifecycle commands expect `adb` and `emulator` to be available via `PATH` or discoverable
through `ANDROID_SDK_ROOT` / `ANDROID_HOME`. `avdmanager` is recommended when you need to create or
inspect AVD definitions outside `android-emu-agent`.

## Contents

- Commands
- Target Selectors
- Swipe and Scroll Directions
- Wait Options

## Commands

### CLI

- `version` Show version information.

### Skills

Install this skill into a coding agent's skill directory. Use when the user asks to set up, install,
or refresh the Android Emu Agent skill for their agent.

- `skills install` Install the bundled skill (default agent: `claude`).
- `skills list` Show where the skill is installed and which version.
- `skills path` Print the bundled skill's source directory.

```bash
# Install for Claude Code (global) or Codex
android-emu-agent skills install --agent claude
android-emu-agent skills install --agent codex

# Project-scoped install (committed with the repo)
android-emu-agent skills install --agent claude --project

# Any other agent: install into an explicit directory
android-emu-agent skills install --dir ~/.config/some-agent/skills

# Replace a directory the CLI did not create
android-emu-agent skills install --force
```

Output interpretation: `mode` is `symlink` when installed from a source checkout (edits apply
immediately) and `copy` otherwise. After upgrading the CLI, re-run `skills install` to refresh a
copied skill. `npx skills add alehkot/android-emu-agent` is an equivalent path for agents supported
by that installer.

### Daemon

- `daemon start` Start the background daemon.
- `daemon stop` Stop the daemon.
- `daemon status` Check daemon status.

Daemon status reports both raw PID liveness and whether that PID owns the live daemon socket. Stop
refuses to signal a live PID when socket ownership cannot be verified.

### Device

- `device list` List connected devices.
- `device capabilities [--device <serial> | --session <session_id>]` Show selector and subsystem
  capabilities for a target.
- `device set animations <on_or_off> -d <device_serial>` Toggle animations.
- `device set stay_awake <on_or_off> -d <device_serial>` Keep screen awake.
- `device set rotation <orientation> -d <device_serial>` Set rotation (`portrait`, `landscape`,
  `reverse-portrait`, `reverse-landscape`, `auto`).
- `device set wifi <on_or_off> -d <device_serial>` Toggle WiFi.
- `device set mobile <on_or_off> -d <device_serial>` Toggle mobile data.
- `device set doze <on_or_off> -d <device_serial>` Toggle doze mode.

### System

- `system notifications open [--device <serial> | --session <session_id>]` Open the notification
  shade.
- `system notifications close [--device <serial> | --session <session_id>]` Close the notification
  shade.
- `system quick-settings open [--device <serial> | --session <session_id>]` Open Quick Settings.
- `system permissions list <package> [--device <serial> | --session <session_id>]` List requested
  and granted package permissions from `dumpsys package`.
- `system permissions grant <package> <permission> [--device <serial> | --session <session_id>]`
  Grant a runtime permission.
- `system permissions revoke <package> <permission> [--device <serial> | --session <session_id>]`
  Revoke a runtime permission.

System commands use validated package and permission names before invoking shell-backed Android
services. Permission changes are useful for deterministic setup but still depend on Android's
runtime permission rules for the target app and device.

### Session

- `session start -d <device_serial>` Create a new session.
- `session stop <session_id>` End a session, archive any active trace, detach its debugger, and
  remove its ADB forward.
- `session list` List active sessions.
- `session info <session_id>` Session details.

### Trace

- `trace start <session_id> [--label <label>]` Start recording a session trace.
- `trace stop <session_id> [--output <path_or_dir>]` Stop recording and write a `.aea-trace.zip`
  archive. Choose an output outside the trace source directory; an existing archive is replaced only
  after the new ZIP is complete.
- `trace status [--session <session_id>]` List active traces.
- `trace replay <path> [--until-failure]` Return a dry-run replay plan from an archive.
- `trace export <path> [--output <path>]` Export a trace archive to Markdown.

Trace archives record daemon request/response exchanges for the active session, including
`diagnostic_id`, request payloads with sensitive fields redacted, response payloads, status codes,
errors, and artifact paths. Replay is currently a dry-run plan so it never mutates a device by
surprise. Diagnostics and traces redact typed `set_text` input for all JSON task forms: `action`
shorthand, `kind` with `operation`, and `kind` with `op`. If aliases conflict, typed input is
conservatively redacted even for rejected requests. Existing logs and archives are not rewritten;
review artifacts for sensitive app content before sharing.

### Task

- `task validate <task.json|task.aea>` Validate a JSON task spec or human-editable `.aea` script.
- `task run <task.json|task.aea> [--session <session_id>] [--continue-on-failure]` Run ordered task
  steps and verifiers.

Task specs support action steps (`tap`, `long_tap`, `set_text`, `clear`, `back`, `home`, `recents`,
`swipe`), wait/verifier operations (`idle`, `activity`, `text`, `exists`, `gone`), app steps
(`launch`, `force_stop`, `deeplink`), and `ui` `snapshot` steps. Use `verify` on a step for
post-step checks and top-level `verifiers` for final checks. A failed verifier returns
`status=failed` with the failing step or verifier payload.

Both `task validate` and `task run` preflight every step and verifier against the daemon request
models before any action is dispatched. Invalid request fields return `ERR_TASK_INVALID` with their
task location, even with `--continue-on-failure`. This checks request types and modeled choices, not
selector existence, installed packages, or all runtime operation constraints.

Malformed numeric options in `.aea` swipe/wait/verifier lines return `ERR_TASK_SCRIPT_INVALID` with
the source file, line, and option name. Swipe distance must be finite. Fix the reported line and
rerun validation; no device actions run for a script rejected during parsing.

Task scripts use one command per line and compile to the same task harness:

```text
name "login smoke"
session s-abc123
launch com.example.app
wait exists text:"Sign in" timeout_ms=10000
tap text:"Sign in" || id:com.example:id/login
verify exists text:"Email"
expect activity MainActivity
```

The formal parser contract is documented at <https://alehkot.github.io/android-emu-agent/aea-spec/>.

In scripts, quote literal `=` text, such as `set-text id:com.example:id/search "x=y"` or
`wait text "Total=5" timeout_ms=1000`. A fully quoted `"timeout_ms=5000"` is literal text;
`timeout_ms="5000"` is an option. Deep-link query URLs retain their parameters, for example
`deeplink "https://example.com/search?q=android&sort=date"`. Quote URLs containing `#` too.

Selector-value quotes survive script compilation: `tap text:"Sign in" enabled:true`,
`tap desc:"Don't stop"`, and `tap text:"A || B"` preserve the complete label. For a compound
`set-text` target or swipe container, quote the entire selector too, for example
`set-text 'text:"Email address" enabled:true' "agent@example.com"` or
`swipe up container='desc:"Message list" scrollable:true'`. Ordinary text and option values still
use shell-style decoding.

Validate a script before running it:

```bash
android-emu-agent task validate ./checkout-smoke.aea
android-emu-agent task run ./checkout-smoke.aea --session s-abc123 --json
```

Ready-made scripts to copy: <https://github.com/alehkot/android-emu-agent/tree/main/examples/tasks>.

### UI

- `ui snapshot <session_id>` Get actionable UI elements.
- `ui snapshot <session_id> --format text` Compact text output.
- `ui screenshot [<session_id>] [--device <serial> | --session <session_id>] [--pull] [--output <path>]`
  Capture screen image (optionally copy to local path).
- `ui ground <session_id> [--ref <ref>] [--no-screenshot] [--pull]` Create optional
  screenshot-to-ref grounding metadata from the latest snapshot.

Default compact snapshots are actionable and work well on classic XML views plus modern frameworks
such as Compose and Litho. Use `--full` when the target element is not in the default actionable
snapshot (e.g., labels, images, non-clickable containers):

- `ui snapshot <session_id> --full` Include all nodes (not just interactive).
- `ui snapshot <session_id> --raw` Return raw XML hierarchy without issuing refs or advancing the
  session generation (for low-level debugging of the UI tree).

`ui ground` does not run vision, OCR, or image matching. It links existing snapshot refs to
screenshot-space bounds so humans or external vision models can inspect evidence without making
vision mandatory for automation.

### Action

- `action tap <session_id> <target>` Tap an element.
- `action long-tap <session_id> <ref>` Long press.
- `action set-text <session_id> <ref> <text>` Replace the field’s existing text (an empty string
  clears it).
- `action clear <session_id> <ref>` Clear text field.

`set-text` replaces rather than appends, including direct coordinate selectors and coordinate
fallbacks for refs. Coordinate actions focus the target field before replacing or clearing text.

- `action back <session_id>` Press back button.
- `action home <session_id>` Press home button.
- `action recents <session_id>` Open recent apps.
- `action swipe <dir> -s <session_id>` Swipe gesture.
- `action scroll <dir> -s <session_id>` Scroll gesture.

Refs use `^g<generation>a<element>` and therefore identify their source snapshot unambiguously. If a
stale ref can be confidently rebound against the latest snapshot generation, action responses may
return `status=done` with a `warning`. Re-snapshot before the next action.

### Wait

- `wait idle <session_id>` Wait for UI idle.
- `wait activity <session_id> <name>` Wait for activity.
- `wait text <session_id> <text>` Wait for text to appear.
- `wait exists <session_id> --text <text>` Wait for element.
- `wait gone <session_id> --text <text>` Wait for element to disappear.

Use alternate selectors when the element has no visible text but has a resource ID or content
description:

- `wait exists <session_id> --id <id> | --desc <desc> | --ref <ref>` Alternate selectors.
- `wait gone <session_id> --id <id> | --desc <desc> | --ref <ref>` Alternate selectors.
- Rich selector flags: `--text-contains`, `--id-matches`, `--desc-contains`, and `--class`.

`wait exists` and `wait gone` can also heal stale refs when the daemon can confidently rebind the
target against the latest snapshot.

For `activity`, `text`, `exists`, and `gone`, `--timeout-ms` bounds the daemon's entire polling
loop, including device I/O and time between polls. A stalled device call returns `ERR_TIMEOUT`
instead of extending that polling deadline; a result received after the deadline is not a success.
The underlying device call may still finish in its bounded per-device worker pool after the wait
returns. This does not forcibly stop the device operation or its driver's recovery work.

For standalone `wait` and timed `expect` commands, the CLI's HTTP timeout allows the requested wait
duration plus 10 seconds for the daemon response (with a 10-second transport minimum). Omitted or
zero `--timeout-ms` uses the daemon's 10-second default, so its HTTP budget is 20 seconds. This
response allowance does not extend the daemon's condition-wait deadline and does not apply to the
aggregate `task run` request.

### Expect

- `expect idle <session_id>` Assert that UI becomes idle.
- `expect text <session_id> <text>` Assert text appears.
- `expect activity <session_id> <name>` Assert activity appears.
- `expect exists <session_id> --text <text>` Assert an element exists.
- `expect gone <session_id> --text <text>` Assert an element disappears.
- `expect current-app <session_id> [--package <package>] [--activity <activity>]` Assert foreground
  app/activity.
- Rich selector flags: `--text-contains`, `--id-matches`, `--desc-contains`, and `--class`.

Expect commands reuse wait/app primitives but return explicit pass/fail payloads. On failure they
return `ERR_EXPECTATION_FAILED`; `current-app` without an expected package or activity returns
`ERR_EXPECTATION_REQUIRED`.

### App

- `app list --device <serial>` List installed packages. Optional: `--scope all|system|third-party`.
- `app install <apk_path> --device <serial>` Install APK on target device.
- `app uninstall <package> --device <serial>` Uninstall package from target device.
- `app launch <session_id> <package>` Launch an app.
- `app intent <session_id> [--action <action>] [--data <uri>]` Launch an intent.
- `app current --session <session_id>` Show current foreground app/activity.
- `app task-stack --session <session_id>` Show activity task stack.
- `app resolve-intent --session <session_id> [--action <action>] [--data <uri>]` Resolve an intent
  without launching it.
- `app force-stop <session_id> <package>` Force stop app.
- `app reset <session_id> <package>` Clear app data.
- `app deeplink <session_id> <uri>` Open a deep link, including opaque Android URIs such as
  `mailto:`, `tel:`, `content:`, and `market:`.

Use `--activity` to launch a specific screen directly. Use `--wait-debugger` when attaching a
debugger to the app at startup:

- `app list --session <session_id>` List packages via an active session.
- `app uninstall <package> --session <session_id> [--keep-data]` Uninstall package via an active
  session.
- `app launch <session_id> <package> --activity <activity>` Launch a specific activity.
- `app launch <session_id> <package> --wait-debugger` Wait for debugger before app start.
- `app deeplink <session_id> <uri> --wait-debugger` Wait for debugger before intent start.
- `app intent <session_id> ... --wait-debugger` Wait for debugger before intent start.

### Debug

- `debug ping <session_id>` Start the JDI bridge (if needed) and verify JSON-RPC roundtrip.
- `debug attach --session <session_id> --package <package> [--process <process_name>] [--keep-suspended]`
  Attach via JDWP and return VM status.
- `debug status --session <session_id>` Show current debugger connection state.
- `debug observe --session <session_id> [--thread <name>] [--max-frames <n>]` Return fused app,
  latest-snapshot, debugger status, event, logpoint, and optional stack context.
- `debug break set <class_pattern> <line> --session <session_id> [--condition <expr>]`
  `[--log-message <template>] [--capture-stack] [--stack-max-frames <n>]` Set a breakpoint,
  conditional breakpoint, or non-suspending logpoint.
- `debug break list --session <session_id>` List breakpoints and their IDs/status.
- `debug break hits --session <session_id> [--breakpoint-id <id>] [--limit <n>]`
  `[--since-timestamp-ms <epoch_ms>]` Inspect buffered non-suspending logpoint hits without draining
  the event queue.
- `debug break remove <breakpoint_id> --session <session_id>` Remove a breakpoint.
- `debug break-exception set --session <session_id> [--class <pattern>] [--caught/--no-caught]`
  `[--uncaught/--no-uncaught]` Set an exception breakpoint (`--class '*'` catches all exception
  types).
- `debug break-exception list --session <session_id>` List exception breakpoints and IDs/status.
- `debug break-exception remove <breakpoint_id> --session <session_id>` Remove an exception
  breakpoint by ID.
- `debug threads --session <session_id> [--all]` List VM threads (use `--all` to include daemon
  threads).
- `debug stack --session <session_id> [--thread <name>] [--max-frames <n>]` Show coroutine-filtered
  stack frames for a suspended thread.
- `debug inspect <variable_path> --session <session_id> [--thread <name>] [--frame <idx>] [--depth <n>]`
  Inspect a local/object path in a stack frame.
- `debug eval <expression> --session <session_id> [--thread <name>] [--frame <idx>]` Evaluate a
  constrained expression (field access or `toString()`).
- `debug mapping load <path> --session <session_id>` Load ProGuard/R8 mapping for deobfuscated
  class/method/field names.
- `debug mapping clear --session <session_id>` Clear loaded mapping from the active debug bridge.
- `debug step-over --session <session_id> [--thread <name>] [--timeout-seconds <sec>]` Step to the
  next line and return stopped location + locals.
- `debug step-into --session <session_id> [--thread <name>] [--timeout-seconds <sec>]` Step into the
  next call and return stopped location + locals.
- `debug step-out --session <session_id> [--thread <name>] [--timeout-seconds <sec>]` Step out of
  the current method and return stopped location + locals.

The step timeout also extends the bridge RPC and daemon-client deadlines, so values above 30 seconds
are honored end to end.

- `debug resume --session <session_id> [--thread <name>]` Resume one thread (when set) or all
  threads.
- `debug events --session <session_id>` Drain queued debugger events (for example `breakpoint_hit`,
  `breakpoint_resolved`, `logpoint_hit`, `breakpoint_condition_error`, `exception_hit`,
  `exception_breakpoint_resolved`).
- `debug detach --session <session_id>` Detach debugger and clean up ADB forwarding.

Use `--process` when multiple debuggable processes are present (for example
`com.example.app:remote`). If omitted, the main package process is chosen when possible.

Use `--keep-suspended` when attaching to an app started with `--wait-debugger` and you need to set
breakpoints before any app code resumes.

Use `debug observe` when an agent needs one bounded planning payload. It is non-destructive by
default: queued events are peeked, not drained, unless `--drain-events` is set. Use `--no-stack`
when the target thread is running and a stack snapshot is not expected.

Step commands return an Observe-Act-Verify payload with `status`, `location`, `method`, `thread`,
`locals`, `token_usage_estimate`, and `truncated`. If stepping times out, `status=timeout` includes
an actionable remediation hint.

`debug break set` may return `status=pending` when the class is not loaded yet. Keep execution
running and use `debug events` to wait for `breakpoint_resolved`, `breakpoint_invalid`, or
`breakpoint_hit`. Invalid lines on loaded exact classes fail immediately; deferred exact classes
emit `breakpoint_invalid` if the requested line has no executable code. Exception breakpoints can
also resolve later via `exception_breakpoint_resolved`.

`--condition` is parsed at set time and supports value paths, literals (`null`, booleans, numbers,
strings), boolean operators (`!`, `&&`, `||`), comparisons (`==`, `!=`, `>`, `>=`, `<`, `<=`), and
parentheses. Malformed syntax is rejected immediately.

On hit, condition evaluation suspends only when truthy. If runtime evaluation fails (for example a
missing local/field or invalid operand types), the bridge emits `breakpoint_condition_error` and
auto-resumes.

`--log-message` makes a logpoint (non-suspending). Use `{hitCount}` and frame expressions like
`{user.id}` in the template; resolved output arrives as `logpoint_hit`. Interpolated messages and
`debug eval ...toString()` results are capped at 16,000 characters and set `truncated=true` when
shortened.

`--capture-stack` adds stack frames to each `logpoint_hit`. Use `--stack-max-frames` to limit
capture cost. Buffered logpoint history is retained per session and can be queried later with
`debug break hits`.

`debug inspect` returns object IDs (`obj_1`, `obj_2`, ...) for object values. These IDs are valid
only while execution remains suspended; after resume/step they are invalidated and must be
re-captured.

Default token bounds are intentionally small (stack: 10 frames, inspect depth: 1). Use
`--max-frames` or `--depth` to inspect more data when needed.

If the stack is mostly `kotlinx.coroutines`, use `debug step-out` repeatedly until user code
appears.

Do not leave the main thread suspended for more than ~8 seconds to avoid ANR risk.

Debugger startup requires JDK 17+; `ERR_JDK_NOT_FOUND` means `java` is not available through
`PATH`/`JAVA_HOME`, while `ERR_JDK_UNSUPPORTED` reports an old runtime or a missing `jdk.jdi`
module.

Cancelling a pending daemon attach or bridge start triggers resource cleanup before cancellation
propagates. Cleanup waits for any in-flight ADB port allocation or subprocess creation; it is not an
immediate-cancel deadline. Cancelling the CLI alone may leave its daemon request running. Each
attach creates its own local forward without rebinding an existing route.

When a mapping is loaded, stack traces and inspect output show deobfuscated names where the mapping
provides them.

### Artifact

- `artifact save-snapshot <session_id>` Save last snapshot.
- `artifact screenshot [<session_id>] [--device <serial> | --session <session_id>]`
  `[--pull] [--output <path>]` Save screenshot (optionally copy to local path).
- `artifact logs <session_id>` Capture logcat.
- `artifact logs --session <session_id> [--package <pkg>|--app <pkg>] [--type <kind>|--level <lvl>]`
  `[--since <t>]` Capture filtered logcat.
- `artifact bundle <session_id>` Save debug bundle.

Automatically named screenshots, logs, saved snapshots, and debug bundles include a random UUID
suffix. Repeated captures keep separate files even within the same second; use the returned path
instead of constructing a filename from the session and timestamp. Bundles clean up only their own
screenshot and log captures. Explicit output filenames retain replacement behavior.

When `--pull` is set, screenshots are copied to `--output` or the current working directory.

Use `--since` to limit logcat by line count, native logcat timestamp, ISO 8601, or relative time:

- `artifact logs <session_id> --since "01-15 14:30:00.000"` Native logcat timestamp.
- `artifact logs <session_id> --since "2026-02-22T20:24:23Z"` ISO 8601 timestamp.
- `artifact logs <session_id> --since "10m ago"` Relative timestamp.
- `artifact logs <session_id> --since 100` Show last 100 lines.

Artifact log capture is bounded and does not stream. Use `adb -s <emulator-serial> logcat` for a
live stream; the retained `--follow` compatibility flag returns `ERR_LOG_FOLLOW_UNSUPPORTED`.

Use `--type` for friendly log filters (`errors`, `warnings`, `info`, etc.) while `--level` remains a
compatible alias.

### Emulator

- `emulator list-avds` List AVDs known to the Android emulator CLI.
- `emulator start <avd_name>` Start an AVD and wait for boot by default.
- `emulator start <avd_name> --port <port>` Use an even fixed console port from 5554 through 5584.
- `emulator start <avd_name> --snapshot <name> --no-snapshot-save` Start from a named snapshot
  without saving Quick Boot state on exit.
- `emulator start <avd_name> --cold-boot` Start without loading Quick Boot or snapshot state.
- `emulator stop <serial>` Stop a running emulator cleanly.
- `emulator snapshot save <serial> <name>` Save emulator snapshot.
- `emulator snapshot restore <serial> <name>` Restore emulator snapshot and restart the emulator by
  default. Use `--no-restart` for a live console load.

Snapshot names accept 1-128 letters, digits, dots, underscores, or hyphens. Spaces and line breaks
are rejected before the emulator console is contacted. When the console requests authentication,
snapshot commands use the token from `~/.emulator_console_auth_token` automatically.

### Reliability

- `reliability profile <package> --device <serial>` Bounded process, memory, rendering, background,
  exit-info, and ActivityManager event profile.
- `reliability perfetto --device <serial> --duration <seconds>` Capture a bounded native Perfetto
  trace and pull a `.perfetto-trace` artifact.
- `reliability simpleperf <package> --device <serial> --duration <seconds>` Capture a bounded
  simpleperf CPU profile and local text report.
- `reliability screenrecord --device <serial> --duration <seconds>` Capture a bounded screen
  recording artifact.
- `reliability exit-info <package> --device <serial>` App exit reasons (A11+).
- `reliability events --device <serial>` ActivityManager events buffer.
- `reliability bugreport --device <serial>` Capture system bugreport.
- `reliability dropbox list --device <serial>` List DropBoxManager entries.
- `reliability dropbox print <tag> --device <serial>` Print DropBoxManager entry.
- `reliability background <package> --device <serial>` Background restrictions.
- `reliability last-anr --device <serial>` Last ANR summary.
- `reliability jobscheduler <package> --device <serial>` Bounded, package-scoped JobScheduler
  constraints.
- `reliability process <package> --device <serial>` Exact-pid process snapshot (pid/oom/selected
  proc status fields).
- `reliability meminfo <package> --device <serial>` Memory diagnostics (`dumpsys meminfo`).
- `reliability gfxinfo <package> --device <serial>` Rendering diagnostics (`dumpsys gfxinfo`).
- `reliability compile <package> --mode reset|speed --device <serial>` Compile/reset package.
- `reliability always-finish <on_or_off> --device <serial>` Always-finish activities.
- `reliability run-as-ls <package> --device <serial>` List app-private files (run-as).
- `reliability dumpheap <package> --device <serial>` Dump heap profile.
- `reliability sigquit <package> --device <serial>` Thread dump (SIGQUIT).
- `reliability oom-adj <package> --device <serial>` Adjust oom_score_adj.
- `reliability trim-memory <package> --device <serial>` Send trim memory.
- `reliability pull anr --device <serial>` Pull /data/anr (root).
- `reliability pull tombstones --device <serial>` Pull /data/tombstones (root).
- `reliability pull dropbox --device <serial>` Pull /data/system/dropbox (root).

Reliability `--output` values are managed artifact filenames, not paths. Directory components, path
separators, control characters, and names over 200 UTF-8 bytes are rejected.

Use `--output` to control bugreport destination, `--since` to limit events by time, `--keep-remote`
to preserve heap files on-device after pulling:

- `reliability bugreport --device <serial> --output <name>` Choose output filename.
- `reliability events --device <serial> --since <timestamp>` Limit events by time.
- `reliability dumpheap <package> --device <serial> --keep-remote` Keep heap on device.
- `reliability perfetto --session <session_id> --duration 10 --output trace.perfetto-trace`
- `reliability simpleperf <package> --session <session_id> --duration 10 --output cpu.data`
- `reliability screenrecord --session <session_id> --duration 10 --output repro.mp4`

### File

- `file push <local> --device <serial>` Push to /sdcard/Download.
- `file pull <remote> --device <serial>` Pull from shared storage.
- `file find <path> --name <pattern> --device <serial>` Find files/folders + metadata;
  shell-readable paths work without root.
- `file list <path> --device <serial>` List files/folders; shell-readable paths work without root.
- `file app push <pkg> <local> --device <serial>` Push to app-private storage via root or `run-as`
  for a debuggable app.
- `file app pull <pkg> <remote> --device <serial>` Pull from app-private storage via root or
  `run-as` for a debuggable app.

Pulls without `--local` return a timestamp-and-UUID path, preserving repeated and concurrent
results. App-private staging paths are also independent per transfer. Explicit destinations retain
their existing replacement or directory-merge behavior.

See `references/reliability.md` for reliability triage workflows and output interpretation. See
`references/files.md` for file transfer workflows. See `references/workflow-examples.md` for
multi-command examples covering visual grounding, traces, capabilities, intent preflight, and
evidence bundles.

## Target Selectors

Element-targeted action commands accept these selector formats:

- `^g1a1`: generation-qualified element ref from snapshot (preferred; `g1` is generation 1 and `a1`
  is element 1).
- `text:"Sign in"`: match by visible text.
- `id:com.example:id/btn`: match by resource ID.
- `desc:"Open menu"`: match by content description.
- `label:"Open menu"`: label alias for content description.
- `text:"Sign in" enabled:true clickable:true`: add uiautomator2 state filters.
- `text:"Sign in" || id:com.example:id/login`: try fallback selectors in order.
- `coords:540,1200`: target absolute coordinates.

Tap and swipe-container selectors must match exactly one node. If a selector is ambiguous, add
compound id/class/text/state filters or use a fresh snapshot `^ref`; fallback selectors do not skip
an ambiguous earlier alternative.

`tap`, `long-tap`, `set-text`, and `clear` accept a preferred `^ref`, a direct selector, or ordered
`||` fallbacks.

## Swipe and Scroll Directions

```bash
android-emu-agent action swipe <direction> -s <session_id> [--in <target>] [--distance <0-1>]
android-emu-agent action scroll <direction> -s <session_id> [--in <target>] [--distance <0-1>]
```

Directions: `up`, `down`, `left`, `right`

Options:

- `--in <target>`: Constrain the gesture to a container `^ref` or selector; `||` fallbacks are tried
  in order and stop on ambiguity
- `--distance <0-1>`: Gesture distance as fraction of screen (default varies) Must be finite,
  greater than zero, and at most one. Direct swipe requests reject NaN and infinity with
  `ERR_INVALID_DISTANCE` before accessing the device. JSON tasks reject nonfinite swipe distances
  during validation with `ERR_TASK_INVALID`, before any task action runs.
- `--duration <ms>`: Swipe duration in milliseconds (swipe only)

## Wait Options

```bash
# Wait for UI to become idle (animations complete)
android-emu-agent wait idle <session_id> --timeout-ms 5000

# Wait for specific activity
android-emu-agent wait activity <session_id> "MainActivity" --timeout-ms 10000

# Wait for text to appear
android-emu-agent wait text <session_id> "Welcome" --timeout-ms 5000

# Wait for element to exist
android-emu-agent wait exists <session_id> --text "Submit" --timeout-ms 5000
android-emu-agent wait exists <session_id> --id "com.example:id/btn" --timeout-ms 5000

# Wait for element to disappear
android-emu-agent wait gone <session_id> --text "Loading..." --timeout-ms 10000
```

Default timeout: 10000ms (10 seconds)
