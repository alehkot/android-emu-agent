# Troubleshooting

## Error Reference

| Error                 | Cause                      | Solution                                               |
| --------------------- | -------------------------- | ------------------------------------------------------ |
| `ERR_STALE_REF`       | Ref from outdated snapshot | Take fresh snapshot, find element again                |
| `ERR_NOT_FOUND`       | Element not in current UI  | Verify correct screen, try different selector          |
| `ERR_DEVICE_OFFLINE`  | Device disconnected        | Run `device list`, reconnect device                    |
| `ERR_SESSION_EXPIRED` | Session timed out          | Create new session with `session start`                |
| `ERR_BLOCKED_INPUT`   | Dialog/keyboard blocking   | Dismiss blocker with `back`, or `wait idle`            |
| `ERR_TIMEOUT`         | Wait condition never met   | Increase `--timeout-ms` or verify condition is correct |
| `ERR_DAEMON_OFFLINE`  | Daemon not running         | Run `daemon start`                                     |

## Common Issues

### Daemon Won't Start

```bash
uv run android-emu-agent daemon status
uv run android-emu-agent daemon stop
uv run android-emu-agent daemon start
ps aux | grep android-emu-agent
```

### Device Not Appearing

```bash
uv run android-emu-agent device list
adb devices
adb kill-server
adb start-server
```

### Elements Not Appearing in Snapshot

- Element not interactive: use `--full` to see all elements.
- Element in WebView: consider coordinates or WebView-specific handling.
- Element behind dialog: dismiss dialog first.
- Element not yet loaded: `wait idle` and re-snapshot.

```bash
uv run android-emu-agent ui snapshot <session_id> --full
uv run android-emu-agent wait idle <session_id> --timeout-ms 5000
uv run android-emu-agent ui snapshot <session_id>
```

### Actions Not Working

- Element not enabled: check `state.enabled`.
- Element not clickable: tap parent/child or use coordinates.
- Dialog blocking input: dismiss first.
- Animation in progress: `wait idle`.
- Try `long-tap` for stubborn elements.

```bash
uv run android-emu-agent wait idle <session_id> --timeout-ms 3000
uv run android-emu-agent action long-tap <session_id> @a1
```

### App Keeps Crashing

```bash
uv run android-emu-agent app reset <session_id> com.example.app
uv run android-emu-agent wait idle <session_id>
uv run android-emu-agent app launch <session_id> com.example.app
uv run android-emu-agent wait activity <session_id> "MainActivity" --timeout-ms 10000
```

## Debug Tips

```bash
# Complete snapshot (all elements)
uv run android-emu-agent ui snapshot <session_id> --full

# Screenshot for visual debugging (optionally pull to local path)
uv run android-emu-agent artifact screenshot <session_id> --pull --output ./screenshot.png
# Or capture without a session
uv run android-emu-agent ui screenshot --device <serial> --pull

# Recent logcat logs
uv run android-emu-agent artifact logs <session_id>

# Full debug bundle
uv run android-emu-agent artifact bundle <session_id>
```

## Reliability Forensics

```bash
# Why did the app die? (Android 11+)
uv run android-emu-agent reliability exit-info com.example.app --device <serial>

# Timeline of process deaths / ANRs
uv run android-emu-agent reliability events --device <serial> --package com.example.app

# System bugreport (captures /data/anr, /data/tombstones)
uv run android-emu-agent reliability bugreport --device <serial>
```
