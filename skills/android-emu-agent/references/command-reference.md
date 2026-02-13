# Command Reference

> **Read this file when** you need to look up a command, its arguments, or selector syntax.

## Commands

Examples in this repo assume `uv run android-emu-agent <command>`. If you installed the CLI
globally, replace with `android-emu-agent <command>`.

Most commands accept `--json` for machine-readable JSON output (useful for scripting or when you
need to parse structured results programmatically).

### CLI

- `version` Show version information.

### Daemon

- `daemon start` Start the background daemon.
- `daemon stop` Stop the daemon.
- `daemon status` Check daemon status.

### Device

- `device list` List connected devices.
- `device set animations <on_or_off> -d <device_serial>` Toggle animations.
- `device set stay_awake <on_or_off> -d <device_serial>` Keep screen awake.
- `device set rotation <orientation> -d <device_serial>` Set rotation (`portrait`, `landscape`,
  `reverse-portrait`, `reverse-landscape`, `auto`).
- `device set wifi <on_or_off> -d <device_serial>` Toggle WiFi.
- `device set mobile <on_or_off> -d <device_serial>` Toggle mobile data.
- `device set doze <on_or_off> -d <device_serial>` Toggle doze mode.

### Session

- `session start -d <device_serial>` Create a new session.
- `session stop <session_id>` End a session.
- `session list` List active sessions.
- `session info <session_id>` Session details.

### UI

- `ui snapshot <session_id>` Get interactive UI elements.
- `ui snapshot <session_id> --format text` Compact text output.
- `ui screenshot [<session_id>] [--device <serial> | --session <session_id>] [--pull] [--output <path>]`
  Capture screen image (optionally copy to local path).

Use `--full` when the target element is not in the default interactive-only snapshot (e.g., labels,
images, non-clickable containers):

- `ui snapshot <session_id> --full` Include all nodes (not just interactive).
- `ui snapshot <session_id> --raw` Return raw XML hierarchy (for low-level debugging of the UI
  tree).

### Action

- `action tap <session_id> <target>` Tap an element.
- `action long-tap <session_id> <ref>` Long press.
- `action set-text <session_id> <ref> <text>` Enter text.
- `action clear <session_id> <ref>` Clear text field.
- `action back <session_id>` Press back button.
- `action home <session_id>` Press home button.
- `action recents <session_id>` Open recent apps.
- `action swipe <dir> -s <session_id>` Swipe gesture.
- `action scroll <dir> -s <session_id>` Scroll gesture.

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

### App

- `app list --device <serial>` List installed packages. Optional: `--scope all|system|third-party`.
- `app install <apk_path> --device <serial>` Install APK on target device.
- `app launch <session_id> <package>` Launch an app.
- `app intent <session_id> [--action <action>] [--data <uri>]` Launch an intent.
- `app current --session <session_id>` Show current foreground app/activity.
- `app task-stack --session <session_id>` Show activity task stack.
- `app resolve-intent --session <session_id> [--action <action>] [--data <uri>]` Resolve an intent
  without launching it.
- `app force-stop <session_id> <package>` Force stop app.
- `app reset <session_id> <package>` Clear app data.
- `app deeplink <session_id> <uri>` Open a deep link.

Use `--activity` to launch a specific screen directly. Use `--wait-debugger` when attaching a
debugger to the app at startup:

- `app list --session <session_id>` List packages via an active session.
- `app launch <session_id> <package> --activity <activity>` Launch a specific activity.
- `app launch <session_id> <package> --wait-debugger` Wait for debugger before app start.
- `app deeplink <session_id> <uri> --wait-debugger` Wait for debugger before intent start.
- `app intent <session_id> ... --wait-debugger` Wait for debugger before intent start.

### Debug

- `debug ping <session_id>` Start the JDI bridge (if needed) and verify JSON-RPC roundtrip.
- `debug attach --session <session_id> --package <package> [--process <process_name>]` Attach via
  JDWP and return VM status.
- `debug status --session <session_id>` Show current debugger connection state.
- `debug break set <class_pattern> <line> --session <session_id>` Set a breakpoint.
- `debug break list --session <session_id>` List breakpoints and their IDs/status.
- `debug break remove <breakpoint_id> --session <session_id>` Remove a breakpoint.
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
- `debug resume --session <session_id> [--thread <name>]` Resume one thread (when set) or all
  threads.
- `debug events --session <session_id>` Drain queued debugger events (for example `breakpoint_hit`,
  `breakpoint_resolved`).
- `debug detach --session <session_id>` Detach debugger and clean up ADB forwarding.

Use `--process` when multiple debuggable processes are present (for example
`com.example.app:remote`). If omitted, the main package process is chosen when possible.

Step commands return an Observe-Act-Verify payload with `status`, `location`, `method`, `thread`,
`locals`, `token_usage_estimate`, and `truncated`. If stepping times out, `status=timeout` includes
an actionable remediation hint.

`debug break set` may return `status=pending` when the class is not loaded yet. Keep execution
running and use `debug events` to wait for `breakpoint_resolved` / `breakpoint_hit`.

`debug inspect` returns object IDs (`obj_1`, `obj_2`, ...) for object values. These IDs are valid
only while execution remains suspended; after resume/step they are invalidated and must be
re-captured.

Default token bounds are intentionally small (stack: 10 frames, inspect depth: 1). Use
`--max-frames` or `--depth` to inspect more data when needed.

If the stack is mostly `kotlinx.coroutines`, use `debug step-out` repeatedly until user code
appears.

Do not leave the main thread suspended for more than ~8 seconds to avoid ANR risk.

Debugger startup requires JDK 17+; `ERR_JDK_NOT_FOUND` means `java` is not available through
`PATH`/`JAVA_HOME`.

When a mapping is loaded, stack traces and inspect output show deobfuscated names where the mapping
provides them.

### Artifact

- `artifact save-snapshot <session_id>` Save last snapshot.
- `artifact screenshot [<session_id>] [--device <serial> | --session <session_id>]`
  `[--pull] [--output <path>]` Save screenshot (optionally copy to local path).
- `artifact logs <session_id>` Capture logcat.
- `artifact logs --session <session_id> --package <pkg> --level <lvl> [--since <t>] [--follow]`
  Capture filtered logcat.
- `artifact bundle <session_id>` Save debug bundle.

When `--pull` is set, screenshots are copied to `--output` or the current working directory.

Use `--since` to limit logcat by timestamp (`MM-DD HH:MM:SS.mmm`) or line count (integer):

- `artifact logs <session_id> --since "01-15 14:30:00.000"` Limit logcat by timestamp.
- `artifact logs <session_id> --since 100` Show last 100 lines.

### Emulator

- `emulator snapshot save <serial> <name>` Save emulator snapshot.
- `emulator snapshot restore <serial> <name>` Restore emulator snapshot.

### Reliability

- `reliability exit-info <package> --device <serial>` App exit reasons (A11+).
- `reliability events --device <serial>` ActivityManager events buffer.
- `reliability bugreport --device <serial>` Capture system bugreport.
- `reliability dropbox list --device <serial>` List DropBoxManager entries.
- `reliability dropbox print <tag> --device <serial>` Print DropBoxManager entry.
- `reliability background <package> --device <serial>` Background restrictions.
- `reliability last-anr --device <serial>` Last ANR summary.
- `reliability jobscheduler <package> --device <serial>` JobScheduler constraints.
- `reliability process <package> --device <serial>` Process snapshot (pid/oom/proc state).
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

Use `--output` to control bugreport destination, `--since` to limit events by time, `--keep-remote`
to preserve heap files on-device after pulling:

- `reliability bugreport --device <serial> --output <path>` Choose output filename.
- `reliability events --device <serial> --since <timestamp>` Limit events by time.
- `reliability dumpheap <package> --device <serial> --keep-remote` Keep heap on device.

### File

- `file push <local> --device <serial>` Push to /sdcard/Download.
- `file pull <remote> --device <serial>` Pull from shared storage.
- `file find <path> --name <pattern> --device <serial>` Find files/folders + metadata (root).
- `file list <path> --device <serial>` List files/folders (root).
- `file app push <pkg> <local> --device <serial>` Push to app-private storage.
- `file app pull <pkg> <remote> --device <serial>` Pull from app-private storage.

See `references/reliability.md` for reliability triage workflows and output interpretation. See
`references/files.md` for file transfer workflows.

## Target Selectors

The `action tap` command accepts these selector formats:

| Selector     | Example                 | Description                           |
| ------------ | ----------------------- | ------------------------------------- |
| `^ref`       | `^a1`                   | Element ref from snapshot (preferred) |
| `text:"..."` | `text:"Sign in"`        | Match by visible text                 |
| `id:...`     | `id:com.example:id/btn` | Match by resource ID                  |
| `desc:"..."` | `desc:"Open menu"`      | Match by content description          |
| `coords:x,y` | `coords:540,1200`       | Tap at absolute coordinates           |

`long-tap`, `set-text`, and `clear` require an `^ref`.

## Swipe and Scroll Directions

```bash
uv run android-emu-agent action swipe <direction> -s <session_id> [--in <target>] [--distance <0-1>]
uv run android-emu-agent action scroll <direction> -s <session_id> [--in <target>] [--distance <0-1>]
```

Directions: `up`, `down`, `left`, `right`

Options:

- `--in <target>`: Constrain gesture to a container element
- `--distance <0-1>`: Gesture distance as fraction of screen (default varies)
- `--duration <ms>`: Swipe duration in milliseconds (swipe only)

## Wait Options

```bash
# Wait for UI to become idle (animations complete)
uv run android-emu-agent wait idle <session_id> --timeout-ms 5000

# Wait for specific activity
uv run android-emu-agent wait activity <session_id> "MainActivity" --timeout-ms 10000

# Wait for text to appear
uv run android-emu-agent wait text <session_id> "Welcome" --timeout-ms 5000

# Wait for element to exist
uv run android-emu-agent wait exists <session_id> --text "Submit" --timeout-ms 5000
uv run android-emu-agent wait exists <session_id> --id "com.example:id/btn" --timeout-ms 5000

# Wait for element to disappear
uv run android-emu-agent wait gone <session_id> --text "Loading..." --timeout-ms 10000
```

Default timeout: 10000ms (10 seconds)
