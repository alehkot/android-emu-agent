# `android-emu-agent`

LLM-driven Android UI control system

**Usage**:

```console
android-emu-agent [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--install-completion`: Install completion for the current shell.
- `--show-completion`: Show completion for the current shell, to copy it or customize the
  installation.
- `--help`: Show this message and exit.

**Commands**:

- `version`: Show version information.
- `daemon`: Daemon lifecycle commands
- `device`: Device management commands
- `session`: Session management commands
- `ui`: UI observation commands
- `action`: Action execution commands
- `wait`: Wait/synchronization commands
- `app`: App management commands
- `artifact`: Artifact and debugging commands
- `emulator`: Emulator management commands
- `reliability`: Reliability and forensics commands
- `file`: File transfer commands

## `android-emu-agent version`

Show version information.

**Usage**:

```console
android-emu-agent version [OPTIONS]
```

**Options**:

- `--help`: Show this message and exit.

## `android-emu-agent daemon`

Daemon lifecycle commands

**Usage**:

```console
android-emu-agent daemon [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `start`: Start the daemon process.
- `stop`: Stop the daemon process.
- `status`: Show daemon status.

### `android-emu-agent daemon start`

Start the daemon process.

**Usage**:

```console
android-emu-agent daemon start [OPTIONS]
```

**Options**:

- `--help`: Show this message and exit.

### `android-emu-agent daemon stop`

Stop the daemon process.

**Usage**:

```console
android-emu-agent daemon stop [OPTIONS]
```

**Options**:

- `--help`: Show this message and exit.

### `android-emu-agent daemon status`

Show daemon status.

**Usage**:

```console
android-emu-agent daemon status [OPTIONS]
```

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent device`

Device management commands

**Usage**:

```console
android-emu-agent device [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `list`: List connected devices.
- `set`: Determinism controls

### `android-emu-agent device list`

List connected devices.

**Usage**:

```console
android-emu-agent device list [OPTIONS]
```

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent device set`

Determinism controls

**Usage**:

```console
android-emu-agent device set [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `animations`: Enable or disable system animations.
- `stay_awake`: Enable or disable stay-awake.
- `rotation`: Set screen rotation.
- `wifi`: Enable or disable WiFi.
- `mobile`: Enable or disable mobile data.
- `doze`: Force device into or out of doze mode.

#### `android-emu-agent device set animations`

Enable or disable system animations.

**Usage**:

```console
android-emu-agent device set animations [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent device set stay_awake`

Enable or disable stay-awake.

**Usage**:

```console
android-emu-agent device set stay_awake [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent device set rotation`

Set screen rotation.

**Usage**:

```console
android-emu-agent device set rotation [OPTIONS] ORIENTATION
```

**Arguments**:

- `ORIENTATION`: portrait|landscape|reverse-portrait|reverse-landscape|auto [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent device set wifi`

Enable or disable WiFi.

**Usage**:

```console
android-emu-agent device set wifi [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent device set mobile`

Enable or disable mobile data.

**Usage**:

```console
android-emu-agent device set mobile [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent device set doze`

Force device into or out of doze mode.

**Usage**:

```console
android-emu-agent device set doze [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent session`

Session management commands

**Usage**:

```console
android-emu-agent session [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `start`: Start a new session on a device.
- `stop`: Stop a session.
- `info`: Show session info.
- `list`: List active sessions.

### `android-emu-agent session start`

Start a new session on a device.

**Usage**:

```console
android-emu-agent session start [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent session stop`

Stop a session.

**Usage**:

```console
android-emu-agent session stop [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent session info`

Show session info.

**Usage**:

```console
android-emu-agent session info [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent session list`

List active sessions.

**Usage**:

```console
android-emu-agent session list [OPTIONS]
```

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent ui`

UI observation commands

**Usage**:

```console
android-emu-agent ui [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `snapshot`: Take a UI snapshot.
- `screenshot`: Capture a screenshot.

### `android-emu-agent ui snapshot`

Take a UI snapshot.

Modes (mutually exclusive):

- Default (compact): Interactive elements only, JSON format
- --full: All elements, JSON format
- --raw: Original XML hierarchy string

**Usage**:

```console
android-emu-agent ui snapshot [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--full`: Include all nodes (JSON)
- `--raw`: Return raw XML hierarchy
- `-f, --format TEXT`: Output format: json|text [default: json]
- `--help`: Show this message and exit.

### `android-emu-agent ui screenshot`

Capture a screenshot.

**Usage**:

```console
android-emu-agent ui screenshot [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--pull`: Copy screenshot to local path
- `-o, --output TEXT`: Output path (file or directory)
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent action`

Action execution commands

**Usage**:

```console
android-emu-agent action [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `tap`: Tap an element.
- `long-tap`: Long tap an element.
- `set-text`: Set text on an element.
- `clear`: Clear text.
- `back`: Press back.
- `home`: Press home.
- `recents`: Press recents.
- `swipe`: Perform swipe gesture.
- `scroll`: Scroll in a direction (alias for swipe).

### `android-emu-agent action tap`

Tap an element.

**Usage**:

```console
android-emu-agent action tap [OPTIONS] SESSION_ID REF
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `REF`: Element ref (^a1) [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action long-tap`

Long tap an element.

**Usage**:

```console
android-emu-agent action long-tap [OPTIONS] SESSION_ID REF
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `REF`: Element ref (^a1) [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action set-text`

Set text on an element.

**Usage**:

```console
android-emu-agent action set-text [OPTIONS] SESSION_ID REF TEXT
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `REF`: Element ref (^a1) [required]
- `TEXT`: Text to set [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action clear`

Clear text.

**Usage**:

```console
android-emu-agent action clear [OPTIONS] SESSION_ID REF
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `REF`: Element ref (^a1) [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action back`

Press back.

**Usage**:

```console
android-emu-agent action back [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action home`

Press home.

**Usage**:

```console
android-emu-agent action home [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action recents`

Press recents.

**Usage**:

```console
android-emu-agent action recents [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action swipe`

Perform swipe gesture.

**Usage**:

```console
android-emu-agent action swipe [OPTIONS] DIRECTION
```

**Arguments**:

- `DIRECTION`: Direction: up, down, left, right [required]

**Options**:

- `-s, --session TEXT`: Session ID [required]
- `--in TEXT`: Container ^ref or selector
- `-d, --distance FLOAT`: Swipe distance (0.0-1.0) [default: 0.8]
- `--duration INTEGER`: Swipe duration in ms [default: 300]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent action scroll`

Scroll in a direction (alias for swipe).

**Usage**:

```console
android-emu-agent action scroll [OPTIONS] DIRECTION
```

**Arguments**:

- `DIRECTION`: Direction: up, down, left, right [required]

**Options**:

- `-s, --session TEXT`: Session ID [required]
- `--in TEXT`: Container ^ref or selector
- `-d, --distance FLOAT`: Scroll distance (0.0-1.0) [default: 0.8]
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent wait`

Wait/synchronization commands

**Usage**:

```console
android-emu-agent wait [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `idle`: Wait for UI idle.
- `activity`: Wait for an activity to appear.
- `text`: Wait for text to appear.
- `exists`: Wait for element to exist.
- `gone`: Wait for element to disappear.

### `android-emu-agent wait idle`

Wait for UI idle.

**Usage**:

```console
android-emu-agent wait idle [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--timeout-ms INTEGER`: Timeout in ms
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent wait activity`

Wait for an activity to appear.

**Usage**:

```console
android-emu-agent wait activity [OPTIONS] SESSION_ID ACTIVITY
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `ACTIVITY`: Activity substring [required]

**Options**:

- `--timeout-ms INTEGER`: Timeout in ms
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent wait text`

Wait for text to appear.

**Usage**:

```console
android-emu-agent wait text [OPTIONS] SESSION_ID TEXT
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `TEXT`: Text to wait for [required]

**Options**:

- `--timeout-ms INTEGER`: Timeout in ms
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent wait exists`

Wait for element to exist.

**Usage**:

```console
android-emu-agent wait exists [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--ref TEXT`: Element ref (^a1)
- `--text TEXT`: Text selector
- `--id TEXT`: Resource ID selector
- `--desc TEXT`: Content-desc selector
- `--timeout-ms INTEGER`: Timeout in ms
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent wait gone`

Wait for element to disappear.

**Usage**:

```console
android-emu-agent wait gone [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--ref TEXT`: Element ref (^a1)
- `--text TEXT`: Text selector
- `--id TEXT`: Resource ID selector
- `--desc TEXT`: Content-desc selector
- `--timeout-ms INTEGER`: Timeout in ms
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent app`

App management commands

**Usage**:

```console
android-emu-agent app [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `install`: Install an APK on the target device.
- `reset`: Clear app data for a package.
- `launch`: Launch an app.
- `force-stop`: Force stop an app.
- `deeplink`: Open a deeplink URI.
- `intent`: Launch an explicit or implicit intent.
- `list`: List installed packages.
- `current`: Show current foreground app/activity.
- `task-stack`: Show current task stack.
- `resolve-intent`: Resolve an intent target without launching...

### `android-emu-agent app install`

Install an APK on the target device.

**Usage**:

```console
android-emu-agent app install [OPTIONS] APK_PATH
```

**Arguments**:

- `APK_PATH`: Local APK path [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--replace / --no-replace`: Replace existing app [default: replace]
- `--grant-permissions`: Grant all runtime permissions
- `--allow-downgrade`: Allow version-code downgrade
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app reset`

Clear app data for a package.

**Usage**:

```console
android-emu-agent app reset [OPTIONS] SESSION_ID PACKAGE
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `PACKAGE`: Package name [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app launch`

Launch an app.

**Usage**:

```console
android-emu-agent app launch [OPTIONS] SESSION_ID PACKAGE
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `PACKAGE`: Package name [required]

**Options**:

- `-a, --activity TEXT`: Activity name
- `--wait-debugger`: Start with -D and wait for debugger
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app force-stop`

Force stop an app.

**Usage**:

```console
android-emu-agent app force-stop [OPTIONS] SESSION_ID PACKAGE
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `PACKAGE`: Package name [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app deeplink`

Open a deeplink URI.

**Usage**:

```console
android-emu-agent app deeplink [OPTIONS] SESSION_ID URI
```

**Arguments**:

- `SESSION_ID`: Session ID [required]
- `URI`: URI to open [required]

**Options**:

- `--wait-debugger`: Start with -D and wait for debugger
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app intent`

Launch an explicit or implicit intent.

**Usage**:

```console
android-emu-agent app intent [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `-a, --action TEXT`: Intent action
- `--data TEXT`: Intent data URI
- `-n, --component TEXT`: Explicit component (package/.Activity)
- `-p, --package TEXT`: Target package
- `--wait-debugger`: Start with -D and wait for debugger
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app list`

List installed packages.

**Usage**:

```console
android-emu-agent app list [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--scope TEXT`: all|system|third-party [default: all]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app current`

Show current foreground app/activity.

**Usage**:

```console
android-emu-agent app current [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app task-stack`

Show current task stack.

**Usage**:

```console
android-emu-agent app task-stack [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent app resolve-intent`

Resolve an intent target without launching it.

**Usage**:

```console
android-emu-agent app resolve-intent [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-s, --session TEXT`: Session ID
- `-a, --action TEXT`: Intent action
- `--data TEXT`: Intent data URI
- `-n, --component TEXT`: Explicit component (package/.Activity)
- `-p, --package TEXT`: Target package
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent artifact`

Artifact and debugging commands

**Usage**:

```console
android-emu-agent artifact [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `save-snapshot`: Save the last snapshot to disk.
- `screenshot`: Capture a screenshot artifact.
- `logs`: Pull logcat logs.
- `bundle`: Create a debug bundle.

### `android-emu-agent artifact save-snapshot`

Save the last snapshot to disk.

**Usage**:

```console
android-emu-agent artifact save-snapshot [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent artifact screenshot`

Capture a screenshot artifact.

**Usage**:

```console
android-emu-agent artifact screenshot [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--pull`: Copy screenshot to local path
- `-o, --output TEXT`: Output path (file or directory)
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent artifact logs`

Pull logcat logs.

**Usage**:

```console
android-emu-agent artifact logs [OPTIONS] [SESSION_ID]
```

**Arguments**:

- `[SESSION_ID]`: Session ID

**Options**:

- `-s, --session TEXT`: Session ID
- `-p, --package TEXT`: Filter by package
- `--level TEXT`: Log level (v|d|i|w|e|f|s or verbose/debug/...)
- `--since TEXT`: Logcat -t value: timestamp or line count
- `--follow`: Follow logs (live stream)
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent artifact bundle`

Create a debug bundle.

**Usage**:

```console
android-emu-agent artifact bundle [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent emulator`

Emulator management commands

**Usage**:

```console
android-emu-agent emulator [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `snapshot`: Emulator snapshot commands

### `android-emu-agent emulator snapshot`

Emulator snapshot commands

**Usage**:

```console
android-emu-agent emulator snapshot [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `save`: Save emulator snapshot.
- `restore`: Restore emulator snapshot.

#### `android-emu-agent emulator snapshot save`

Save emulator snapshot.

**Usage**:

```console
android-emu-agent emulator snapshot save [OPTIONS] SERIAL NAME
```

**Arguments**:

- `SERIAL`: Emulator serial (e.g., emulator-5554) [required]
- `NAME`: Snapshot name [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent emulator snapshot restore`

Restore emulator snapshot.

**Usage**:

```console
android-emu-agent emulator snapshot restore [OPTIONS] SERIAL NAME
```

**Arguments**:

- `SERIAL`: Emulator serial (e.g., emulator-5554) [required]
- `NAME`: Snapshot name [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent reliability`

Reliability and forensics commands

**Usage**:

```console
android-emu-agent reliability [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `exit-info`: Show ApplicationExitInfo for a package.
- `bugreport`: Capture a system bugreport.
- `events`: Dump ActivityManager events log.
- `background`: Check background restrictions and standby...
- `last-anr`: Show the last ANR summary from...
- `jobscheduler`: Inspect JobScheduler constraints for a...
- `process`: Inspect process state for a package.
- `meminfo`: Dump memory info for a package.
- `gfxinfo`: Dump graphics/frame timing info for a...
- `compile`: Reset or force package compilation.
- `always-finish`: Toggle always-finish-activities developer...
- `run-as-ls`: List app-private files for debuggable apps...
- `dumpheap`: Dump a heap profile and pull it locally.
- `sigquit`: Send SIGQUIT to dump thread stacks.
- `oom-adj`: Adjust oom_score_adj to make a process...
- `trim-memory`: Send a trim memory signal to the app.
- `dropbox`: DropBoxManager commands
- `pull`: Pull protected artifacts (rooted/emulator)

### `android-emu-agent reliability exit-info`

Show ApplicationExitInfo for a package.

**Usage**:

```console
android-emu-agent reliability exit-info [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability bugreport`

Capture a system bugreport.

**Usage**:

```console
android-emu-agent reliability bugreport [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--output TEXT`: Output filename (.zip)
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability events`

Dump ActivityManager events log.

**Usage**:

```console
android-emu-agent reliability events [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--pattern TEXT`: Regex filter for events
- `--package TEXT`: Filter for package name
- `--since TEXT`: Logcat -t value: timestamp (MM-DD HH:MM:SS.mmm) or line count
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability background`

Check background restrictions and standby bucket.

**Usage**:

```console
android-emu-agent reliability background [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability last-anr`

Show the last ANR summary from ActivityManager.

**Usage**:

```console
android-emu-agent reliability last-anr [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability jobscheduler`

Inspect JobScheduler constraints for a package.

**Usage**:

```console
android-emu-agent reliability jobscheduler [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability process`

Inspect process state for a package.

**Usage**:

```console
android-emu-agent reliability process [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability meminfo`

Dump memory info for a package.

**Usage**:

```console
android-emu-agent reliability meminfo [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability gfxinfo`

Dump graphics/frame timing info for a package.

**Usage**:

```console
android-emu-agent reliability gfxinfo [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability compile`

Reset or force package compilation.

**Usage**:

```console
android-emu-agent reliability compile [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `--mode TEXT`: reset|speed [default: reset]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability always-finish`

Toggle always-finish-activities developer setting.

**Usage**:

```console
android-emu-agent reliability always-finish [OPTIONS] STATE
```

**Arguments**:

- `STATE`: on|off [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability run-as-ls`

List app-private files for debuggable apps using run-as.

**Usage**:

```console
android-emu-agent reliability run-as-ls [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `--path TEXT`: Relative path under app data [default: files/]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability dumpheap`

Dump a heap profile and pull it locally.

**Usage**:

```console
android-emu-agent reliability dumpheap [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `--keep-remote`: Keep heap on device
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability sigquit`

Send SIGQUIT to dump thread stacks.

**Usage**:

```console
android-emu-agent reliability sigquit [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability oom-adj`

Adjust oom_score_adj to make a process more killable (root required).

**Usage**:

```console
android-emu-agent reliability oom-adj [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `--score INTEGER`: oom_score_adj value [default: 1000]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability trim-memory`

Send a trim memory signal to the app.

**Usage**:

```console
android-emu-agent reliability trim-memory [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `--level TEXT`: Trim level constant [default: RUNNING_CRITICAL]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability dropbox`

DropBoxManager commands

**Usage**:

```console
android-emu-agent reliability dropbox [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `list`: List DropBoxManager entries.
- `print`: Print a DropBoxManager entry.

#### `android-emu-agent reliability dropbox list`

List DropBoxManager entries.

**Usage**:

```console
android-emu-agent reliability dropbox list [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--package TEXT`: Filter for package name
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent reliability dropbox print`

Print a DropBoxManager entry.

**Usage**:

```console
android-emu-agent reliability dropbox print [OPTIONS] TAG
```

**Arguments**:

- `TAG`: DropBox tag (e.g., data_app_crash) [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent reliability pull`

Pull protected artifacts (rooted/emulator)

**Usage**:

```console
android-emu-agent reliability pull [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `anr`: Pull /data/anr (root required).
- `tombstones`: Pull /data/tombstones (root required).
- `dropbox`: Pull /data/system/dropbox (root required).

#### `android-emu-agent reliability pull anr`

Pull /data/anr (root required).

**Usage**:

```console
android-emu-agent reliability pull anr [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent reliability pull tombstones`

Pull /data/tombstones (root required).

**Usage**:

```console
android-emu-agent reliability pull tombstones [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent reliability pull dropbox`

Pull /data/system/dropbox (root required).

**Usage**:

```console
android-emu-agent reliability pull dropbox [OPTIONS]
```

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

## `android-emu-agent file`

File transfer commands

**Usage**:

```console
android-emu-agent file [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `push`: Push a local file to shared storage (sdcard).
- `pull`: Pull a file from shared storage (sdcard).
- `find`: Find files/folders and return metadata...
- `list`: List files/folders in a directory...
- `app`: App-private file operations (rooted/emulator)

### `android-emu-agent file push`

Push a local file to shared storage (sdcard).

**Usage**:

```console
android-emu-agent file push [OPTIONS] LOCAL_PATH
```

**Arguments**:

- `LOCAL_PATH`: Local file or directory [required]

**Options**:

- `--remote TEXT`: Remote path (default: /sdcard/Download/&lt;name&gt;)
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent file pull`

Pull a file from shared storage (sdcard).

**Usage**:

```console
android-emu-agent file pull [OPTIONS] REMOTE_PATH
```

**Arguments**:

- `REMOTE_PATH`: Remote file or directory [required]

**Options**:

- `--local TEXT`: Local output path
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent file find`

Find files/folders and return metadata (rooted/emulator).

**Usage**:

```console
android-emu-agent file find [OPTIONS] PATH
```

**Arguments**:

- `PATH`: Root directory to search [required]

**Options**:

- `--name TEXT`: Filename glob (e.g. _.db or cache_) [required]
- `--type TEXT`: file|dir|any [default: any]
- `--max-depth INTEGER`: Max directory depth [default: 4]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent file list`

List files/folders in a directory (rooted/emulator).

**Usage**:

```console
android-emu-agent file list [OPTIONS] PATH
```

**Arguments**:

- `PATH`: Directory to list [required]

**Options**:

- `--type TEXT`: file|dir|any [default: any]
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent file app`

App-private file operations (rooted/emulator)

**Usage**:

```console
android-emu-agent file app [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `push`: Push a file into app-private storage...
- `pull`: Pull a file from app-private storage...

#### `android-emu-agent file app push`

Push a file into app-private storage (rooted/emulator).

**Usage**:

```console
android-emu-agent file app push [OPTIONS] PACKAGE LOCAL_PATH
```

**Arguments**:

- `PACKAGE`: Package name [required]
- `LOCAL_PATH`: Local file or directory [required]

**Options**:

- `--remote TEXT`: App data path (default: files/&lt;name&gt;)
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent file app pull`

Pull a file from app-private storage (rooted/emulator).

**Usage**:

```console
android-emu-agent file app pull [OPTIONS] PACKAGE REMOTE_PATH
```

**Arguments**:

- `PACKAGE`: Package name [required]
- `REMOTE_PATH`: App data path (relative or absolute) [required]

**Options**:

- `--local TEXT`: Local output path
- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--json`: Output JSON
- `--help`: Show this message and exit.
