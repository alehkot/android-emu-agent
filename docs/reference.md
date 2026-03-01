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
- `debug`: Debugger commands (JDI Bridge)
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

## `android-emu-agent debug`

Debugger commands (JDI Bridge)

**Usage**:

```console
android-emu-agent debug [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `ping`: Ping the JDI Bridge to verify it starts...
- `attach`: Attach the debugger to a running app&#x27;s JVM.
- `detach`: Detach the debugger from a session.
- `status`: Get the debug session status.
- `threads`: List debugger-visible VM threads.
- `events`: Drain and return queued debugger events.
- `stack`: Return stack trace for a debugger thread.
- `inspect`: Inspect a variable path in the selected...
- `eval`: Evaluate a constrained expression in the...
- `step-over`: Step over and return stopped state...
- `step-into`: Step into and return stopped state...
- `step-out`: Step out and return stopped state atomically.
- `resume`: Resume one thread or all threads.
- `break`: Breakpoint commands
- `break-exception`: Exception breakpoint commands
- `mapping`: ProGuard/R8 mapping commands

### `android-emu-agent debug ping`

Ping the JDI Bridge to verify it starts and responds.

**Usage**:

```console
android-emu-agent debug ping [OPTIONS] SESSION_ID
```

**Arguments**:

- `SESSION_ID`: Session ID [required]

**Options**:

- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug attach`

Attach the debugger to a running app&#x27;s JVM.

**Usage**:

```console
android-emu-agent debug attach [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--package TEXT`: App package name [required]
- `--process TEXT`: Optional process name (e.g. com.example.app:remote) when multiple are debuggable
- `--keep-suspended`: Do not auto-resume a fully suspended VM on attach
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug detach`

Detach the debugger from a session.

**Usage**:

```console
android-emu-agent debug detach [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug status`

Get the debug session status.

**Usage**:

```console
android-emu-agent debug status [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug threads`

List debugger-visible VM threads.

**Usage**:

```console
android-emu-agent debug threads [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--all`: Include daemon/internal threads and increase output limit
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug events`

Drain and return queued debugger events.

**Usage**:

```console
android-emu-agent debug events [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug stack`

Return stack trace for a debugger thread.

**Usage**:

```console
android-emu-agent debug stack [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--max-frames INTEGER`: Maximum frames to return [default: 10]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug inspect`

Inspect a variable path in the selected frame.

**Usage**:

```console
android-emu-agent debug inspect [OPTIONS] VARIABLE_PATH
```

**Arguments**:

- `VARIABLE_PATH`: Variable path (e.g. user.profile.name or obj_1) [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--frame INTEGER`: Zero-based frame index [default: 0]
- `--depth INTEGER`: Nested expansion depth (1-3) [default: 1]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug eval`

Evaluate a constrained expression in the selected frame.

**Usage**:

```console
android-emu-agent debug eval [OPTIONS] EXPRESSION
```

**Arguments**:

- `EXPRESSION`: Expression (field access or toString()) [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--frame INTEGER`: Zero-based frame index [default: 0]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug step-over`

Step over and return stopped state atomically.

**Usage**:

```console
android-emu-agent debug step-over [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--timeout-seconds FLOAT`: Step timeout in seconds [default: 10.0]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug step-into`

Step into and return stopped state atomically.

**Usage**:

```console
android-emu-agent debug step-into [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--timeout-seconds FLOAT`: Step timeout in seconds [default: 10.0]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug step-out`

Step out and return stopped state atomically.

**Usage**:

```console
android-emu-agent debug step-out [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Thread name [default: main]
- `--timeout-seconds FLOAT`: Step timeout in seconds [default: 10.0]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug resume`

Resume one thread or all threads.

**Usage**:

```console
android-emu-agent debug resume [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--thread TEXT`: Optional thread name; omit to resume all threads
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug break`

Breakpoint commands

**Usage**:

```console
android-emu-agent debug break [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `set`: Set a breakpoint by class pattern and line...
- `remove`: Remove a breakpoint by ID.
- `list`: List active breakpoints.
- `hits`: List buffered non-suspending breakpoint hits.

#### `android-emu-agent debug break set`

Set a breakpoint by class pattern and line number.

**Usage**:

```console
android-emu-agent debug break set [OPTIONS] CLASS_PATTERN LINE
```

**Arguments**:

- `CLASS_PATTERN`: Class pattern (e.g. com.example.MainActivity) [required]
- `LINE`: 1-based source line number [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--condition TEXT`: Condition expression
- `--log-message TEXT`: Log message template with {expr} placeholders (non-suspending logpoint)
- `--capture-stack`: Capture stack on logpoint hit
- `--stack-max-frames INTEGER RANGE`: Frames to capture per logpoint hit [default: 8; x&gt;=1]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug break remove`

Remove a breakpoint by ID.

**Usage**:

```console
android-emu-agent debug break remove [OPTIONS] BREAKPOINT_ID
```

**Arguments**:

- `BREAKPOINT_ID`: Breakpoint ID [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug break list`

List active breakpoints.

**Usage**:

```console
android-emu-agent debug break list [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug break hits`

List buffered non-suspending breakpoint hits.

**Usage**:

```console
android-emu-agent debug break hits [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--breakpoint-id INTEGER`: Optional breakpoint ID filter
- `--limit INTEGER`: Maximum buffered hits to return [default: 100]
- `--since TEXT`: Lower-bound timestamp (epoch ms, ISO 8601, or relative e.g. &#x27;10m ago&#x27;)
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug break-exception`

Exception breakpoint commands

**Usage**:

```console
android-emu-agent debug break-exception [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `set`: Set an exception breakpoint by class pattern.
- `remove`: Remove an exception breakpoint by ID.
- `list`: List active exception breakpoints.

#### `android-emu-agent debug break-exception set`

Set an exception breakpoint by class pattern.

**Usage**:

```console
android-emu-agent debug break-exception set [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--class TEXT`: Exception class pattern or &#x27;_&#x27; for all [default: _]
- `--caught / --no-caught`: Break on caught exceptions [default: caught]
- `--uncaught / --no-uncaught`: Break on uncaught exceptions [default: uncaught]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug break-exception remove`

Remove an exception breakpoint by ID.

**Usage**:

```console
android-emu-agent debug break-exception remove [OPTIONS] BREAKPOINT_ID
```

**Arguments**:

- `BREAKPOINT_ID`: Exception breakpoint ID [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug break-exception list`

List active exception breakpoints.

**Usage**:

```console
android-emu-agent debug break-exception list [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

### `android-emu-agent debug mapping`

ProGuard/R8 mapping commands

**Usage**:

```console
android-emu-agent debug mapping [OPTIONS] COMMAND [ARGS]...
```

**Options**:

- `--help`: Show this message and exit.

**Commands**:

- `load`: Load a ProGuard/R8 mapping file for...
- `clear`: Clear the loaded ProGuard/R8 mapping from...

#### `android-emu-agent debug mapping load`

Load a ProGuard/R8 mapping file for deobfuscation.

**Usage**:

```console
android-emu-agent debug mapping load [OPTIONS] PATH
```

**Arguments**:

- `PATH`: Path to ProGuard/R8 mapping.txt [required]

**Options**:

- `--session TEXT`: Session ID [required]
- `--json`: Output JSON
- `--help`: Show this message and exit.

#### `android-emu-agent debug mapping clear`

Clear the loaded ProGuard/R8 mapping from this debug session.

**Usage**:

```console
android-emu-agent debug mapping clear [OPTIONS]
```

**Options**:

- `--session TEXT`: Session ID [required]
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
- `uninstall`: Uninstall a package from the target device.
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

### `android-emu-agent app uninstall`

Uninstall a package from the target device.

**Usage**:

```console
android-emu-agent app uninstall [OPTIONS] PACKAGE
```

**Arguments**:

- `PACKAGE`: Package name [required]

**Options**:

- `-d, --device TEXT`: Device serial
- `-s, --session TEXT`: Session ID
- `--keep-data`: Keep app data and cache directories
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
- `-p, --package, --app TEXT`: Filter to logs for one app package
- `--level TEXT`: Deprecated alias for --type (v|d|i|w|e|f|s or verbose/debug/...)
- `--type TEXT`: Log type (errors, warnings, info, debug, verbose, fatal, silent)
- `--since TEXT`: Since filter: line count, logcat timestamp, ISO 8601, or relative (e.g. &#x27;10m
  ago&#x27;)
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
