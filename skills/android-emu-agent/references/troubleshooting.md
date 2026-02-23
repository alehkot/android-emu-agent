# Troubleshooting

> **Read this file when** you hit an error code, unexpected behavior, or need debug tips.

## Quick Triage

Match your symptom to the right section:

- **Got an error code** (e.g., `ERR_STALE_REF`) → see Error Reference table below
- **Action failed mid-flow** → see `references/recovery.md` for the 3-level recovery protocol
- **No error but wrong behavior** (elements missing, actions not working) → see Common Issues below
- **App crashing or dying** → see `references/reliability.md` for crash/ANR triage workflows
- **Daemon or device problems** → see Common Issues > Daemon Won't Start / Device Not Appearing

## Error Reference

| Error                 | Cause                        | Solution                                               | Recovery        |
| --------------------- | ---------------------------- | ------------------------------------------------------ | --------------- |
| `ERR_STALE_REF`       | Ref from outdated snapshot   | Take fresh snapshot, find element again                | Level 1 (auto)  |
| `ERR_NOT_FOUND`       | Element not in current UI    | Verify correct screen, try different selector          | Level 1 (auto)  |
| `ERR_BLOCKED_INPUT`   | Dialog/keyboard blocking     | Dismiss blocker with `back`, or `wait idle`            | Level 1 (auto)  |
| `ERR_ACTION_FAILED`   | Action dispatched but failed | Re-snapshot, verify target state, retry                | Level 1 (auto)  |
| `ERR_TIMEOUT`         | Wait condition never met     | Increase `--timeout-ms` or verify condition is correct | Level 2 (auto)  |
| `ERR_NO_LOCATOR`      | No locator strategy found    | Use `--full` snapshot, try coordinate-based action     | Level 2 (auto)  |
| `ERR_DEVICE_OFFLINE`  | Device disconnected          | Run `device list`, reconnect device                    | Not recoverable |
| `ERR_SESSION_EXPIRED` | Session timed out            | Create new session with `session start`                | Not recoverable |
| `ERR_DAEMON_OFFLINE`  | Daemon not running           | Run `daemon start`                                     | Not recoverable |

> **Note:** Infrastructure errors (device offline, session expired, daemon offline) cannot be
> recovered automatically. Stop and report to the user.

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
- If in the middle of an action flow and the element has disappeared, follow the recovery protocol
  (`references/recovery.md`) rather than manually debugging.

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
uv run android-emu-agent action long-tap <session_id> ^a1
```

### Action Failure Recovery

When an action fails during an automation flow, use the structured recovery protocol:

- **Level 1 (auto):** Re-snapshot and retry with fresh refs (handles stale refs, missing elements)
- **Level 2 (auto):** Screenshot + full snapshot for visual diagnosis (handles off-screen, dialogs,
  wrong activity)
- **Level 3 (interactive):** Present state and options to user for guidance

See `references/recovery.md` for the full protocol, limits, and decision flowchart.

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
# Filtered logcat for one app (optionally follow)
uv run android-emu-agent artifact logs --session <session_id> --app com.example.app --type errors --since "10m ago" --follow

# Full debug bundle
uv run android-emu-agent artifact bundle <session_id>
```

## Reliability Forensics

For crash, ANR, and process death diagnosis, see `references/reliability.md` which provides a triage
decision tree and step-by-step workflows with output interpretation.
