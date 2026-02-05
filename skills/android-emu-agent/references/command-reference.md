# Command Reference

## Essential Commands

Examples in this repo assume `uv run android-emu-agent <command>`. If you installed the CLI
globally, replace with `android-emu-agent <command>`.

Optional output (when scripting): most commands accept `--json` for machine-readable output.

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

Advanced (when needed):

- `ui snapshot <session_id> --full` Include all nodes (not just interactive).
- `ui snapshot <session_id> --raw` Return raw XML hierarchy.

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

Advanced (when needed):

- `wait exists <session_id> --id <id> | --desc <desc> | --ref <ref>` Alternate selectors.
- `wait gone <session_id> --id <id> | --desc <desc> | --ref <ref>` Alternate selectors.

### App

- `app list --device <serial>` List installed packages. Optional: `--scope all|system|third-party`.
- `app launch <session_id> <package>` Launch an app.
- `app force-stop <session_id> <package>` Force stop app.
- `app reset <session_id> <package>` Clear app data.
- `app deeplink <session_id> <uri>` Open a deep link.

Advanced (when needed):

- `app list --session <session_id>` List packages via an active session.
- `app launch <session_id> <package> --activity <activity>` Launch a specific activity.

### Artifact

- `artifact save-snapshot <session_id>` Save last snapshot.
- `artifact screenshot [<session_id>] [--device <serial> | --session <session_id>]`
  `[--pull] [--output <path>]` Save screenshot (optionally copy to local path).
- `artifact logs <session_id>` Capture logcat.
- `artifact bundle <session_id>` Save debug bundle.

When `--pull` is set, screenshots are copied to `--output` or the current working directory.

Advanced (when needed):

- `artifact logs <session_id> --since <timestamp>` Limit logcat by time (logcat `-t` value).

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

Advanced (when needed):

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

See `references/reliability.md` for the full reliability command set and workflows. See
`references/files.md` for file transfer workflows.

## Target Selectors

The `action tap` command accepts these selector formats:

| Selector     | Example                 | Description                           |
| ------------ | ----------------------- | ------------------------------------- |
| `@ref`       | `@a1`                   | Element ref from snapshot (preferred) |
| `text:"..."` | `text:"Sign in"`        | Match by visible text                 |
| `id:...`     | `id:com.example:id/btn` | Match by resource ID                  |
| `desc:"..."` | `desc:"Open menu"`      | Match by content description          |
| `coords:x,y` | `coords:540,1200`       | Tap at absolute coordinates           |

`long-tap`, `set-text`, and `clear` require an `@ref`.

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
