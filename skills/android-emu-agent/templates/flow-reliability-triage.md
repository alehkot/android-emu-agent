# Flow: Reliability Triage (Crash/ANR)

Goal: Determine why an app died or hung.

## Inputs

- `<serial>` or `<session_id>`
- `<package>`

## Steps (Non-Rooted)

```bash
# 1) Exit reason history (Android 11+)
uv run android-emu-agent reliability exit-info <package> --device <serial>

# 2) Timeline reconstruction
uv run android-emu-agent reliability events --device <serial> --package <package>

# 3) Persistent crash/ANR summaries
uv run android-emu-agent reliability dropbox list --device <serial> --package <package>
uv run android-emu-agent reliability dropbox print data_app_crash --device <serial>
uv run android-emu-agent reliability dropbox print data_app_anr --device <serial>

# 4) Full bugreport (for /data/anr + /data/tombstones)
uv run android-emu-agent reliability bugreport --device <serial>
```

## Steps (Rooted / Emulator)

```bash
# Pull protected artifacts directly
uv run android-emu-agent reliability pull anr --device <serial>
uv run android-emu-agent reliability pull tombstones --device <serial>
uv run android-emu-agent reliability pull dropbox --device <serial>

# If the app is frozen but not crashing, dump stacks
uv run android-emu-agent reliability sigquit <package> --device <serial>
```

## Optional Stress Tests

```bash
# Make it easy for the system to kill the app
uv run android-emu-agent reliability oom-adj <package> --device <serial> --score 1000

# Trigger low-memory handling
uv run android-emu-agent reliability trim-memory <package> --device <serial> --level RUNNING_CRITICAL
```
