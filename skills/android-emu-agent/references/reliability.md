# Reliability & Forensics

Use these commands when diagnosing crashes, ANRs, or silent process death. All reliability commands
accept **either** `--device <serial>` **or** `--session <session_id>`.

## Non-Rooted Devices (Production/QA)

### Why Did It Die? (Exit Info)

```bash
uv run android-emu-agent reliability exit-info com.example.app --device emulator-5554
uv run android-emu-agent reliability exit-info com.example.app --device emulator-5554 --list
```

### Timeline Reconstruction (Events Buffer)

```bash
uv run android-emu-agent reliability events --device emulator-5554
uv run android-emu-agent reliability events --device emulator-5554 --package com.example.app
uv run android-emu-agent reliability events --device emulator-5554 --pattern "am_proc_died|am_anr"
```

Advanced (when needed): limit by time with `--since` (logcat `-t` value).

```bash
uv run android-emu-agent reliability events --device emulator-5554 --since "10m"
```

### Bugreport Bridge (Protected Artifacts)

```bash
uv run android-emu-agent reliability bugreport --device emulator-5554
# Zip saved to ~/.android-emu-agent/artifacts/reliability
```

Advanced (when needed): choose output filename with `--output`.

```bash
uv run android-emu-agent reliability bugreport --device emulator-5554 --output ./bugreport.zip
```

### Persistent Logs (DropBoxManager)

```bash
uv run android-emu-agent reliability dropbox list --device emulator-5554 --package com.example.app
uv run android-emu-agent reliability dropbox print data_app_crash --device emulator-5554
```

### Background Restrictions

```bash
uv run android-emu-agent reliability background com.example.app --device emulator-5554
```

### Process + Resource Snapshot

```bash
uv run android-emu-agent reliability process com.example.app --device emulator-5554
uv run android-emu-agent reliability meminfo com.example.app --device emulator-5554
uv run android-emu-agent reliability gfxinfo com.example.app --device emulator-5554
```

## Rooted Devices / Emulators

### Pull Protected Artifacts (Root Required)

```bash
uv run android-emu-agent reliability pull anr --device emulator-5554
uv run android-emu-agent reliability pull tombstones --device emulator-5554
uv run android-emu-agent reliability pull dropbox --device emulator-5554
```

### Force Thread Dump (SIGQUIT)

```bash
uv run android-emu-agent reliability sigquit com.example.app --device emulator-5554
```

### Chaos Testing

```bash
uv run android-emu-agent reliability oom-adj com.example.app --device emulator-5554 --score 1000
uv run android-emu-agent reliability trim-memory com.example.app --device emulator-5554 --level RUNNING_CRITICAL
```

## Hidden Gems

### Cold vs Warm Start

```bash
uv run android-emu-agent reliability compile com.example.app --device emulator-5554 --mode reset
uv run android-emu-agent reliability compile com.example.app --device emulator-5554 --mode speed
```

### Last ANR Summary

```bash
uv run android-emu-agent reliability last-anr --device emulator-5554
```

### Always-Finish Activities (Lifecycle Stress)

```bash
uv run android-emu-agent reliability always-finish on --device emulator-5554
uv run android-emu-agent reliability always-finish off --device emulator-5554
```

### JobScheduler Diagnostics

```bash
uv run android-emu-agent reliability jobscheduler com.example.app --device emulator-5554
```

### Debuggable App Access (Non-Root)

```bash
uv run android-emu-agent reliability run-as-ls com.example.app --device emulator-5554 --path files/
uv run android-emu-agent reliability dumpheap com.example.app --device emulator-5554
```

Advanced (when needed): keep the heap file on device with `--keep-remote`.

```bash
uv run android-emu-agent reliability dumpheap com.example.app --device emulator-5554 --keep-remote
```
