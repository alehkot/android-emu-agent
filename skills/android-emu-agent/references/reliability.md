# Reliability & Forensics

> **Read this file when** the app crashed, froze (ANR), was killed in the background, or has a
> performance regression. Start with the Triage Decision Tree below.

Use these commands when diagnosing crashes, ANRs, silent process death, or performance issues. All
reliability commands accept **either** `--device <serial>` **or** `--session <session_id>`.

## Triage Decision Tree

Start here when something goes wrong. Follow the path that matches your symptom:

```text
What happened?
  │
  ├─ App crashed or was killed
  │    1. exit-info  → get the exit reason (Android 11+)
  │    2. events     → see the timeline of process deaths
  │    3. dropbox    → get crash stack traces
  │    4. bugreport  → full system capture (if above is insufficient)
  │
  ├─ App froze (ANR)
  │    1. last-anr   → quick ANR summary
  │    2. events     → confirm ANR in timeline
  │    3. sigquit    → force thread dump (root/emulator) to see blocked threads
  │    4. pull anr   → pull /data/anr traces (root/emulator)
  │
  ├─ App killed in background
  │    1. exit-info  → check for OOM or system-initiated kills
  │    2. background → check background restrictions
  │    3. process    → check current oom_adj and process state
  │
  ├─ Performance regression (jank, slow start)
  │    1. gfxinfo    → rendering frame stats
  │    2. meminfo    → memory usage breakdown
  │    3. compile    → reset ART compilation to test cold-start (--mode reset)
  │
  └─ Need to stress-test resilience
       1. always-finish on → force activity destruction on background
       2. oom-adj / trim-memory → simulate memory pressure
       3. compile --mode reset → force unoptimized code paths
```

## Crash / Kill Triage (Non-Rooted)

Run these steps in order. Each step narrows the diagnosis.

### Step 1: Exit Info (Process Death Reasons)

Shows why the system killed the app. Available on Android 11+.

```bash
uv run android-emu-agent reliability exit-info com.example.app --device emulator-5554
uv run android-emu-agent reliability exit-info com.example.app --device emulator-5554 --list
```

**Output interpretation:** Look for `reason` field — common values: `REASON_CRASH` (unhandled
exception), `REASON_ANR` (main thread blocked), `REASON_LOW_MEMORY` (OOM kill),
`REASON_USER_REQUESTED` (force-stop). The `description` field contains the exception or ANR cause.

### Step 2: ActivityManager Events

Timeline of process starts, deaths, and ANRs from the system events buffer.

```bash
uv run android-emu-agent reliability events --device emulator-5554 --package com.example.app
uv run android-emu-agent reliability events --device emulator-5554 --pattern "am_proc_died|am_anr"
```

Use `--since` to limit by time (e.g., `--since "10m"` for last 10 minutes):

```bash
uv run android-emu-agent reliability events --device emulator-5554 --since "10m"
```

**Output interpretation:** Look for `am_proc_died` entries (process killed), `am_anr` (ANR trigger),
`am_crash` (crash). Timestamps show the sequence of events.

### Step 3: DropBoxManager Crash Logs

Persistent crash and ANR stack traces that survive process death.

```bash
uv run android-emu-agent reliability dropbox list --device emulator-5554 --package com.example.app
uv run android-emu-agent reliability dropbox print data_app_crash --device emulator-5554
uv run android-emu-agent reliability dropbox print data_app_anr --device emulator-5554
```

**Output interpretation:** `data_app_crash` entries contain Java stack traces. `data_app_anr`
entries contain the ANR reason and main thread stack.

### Step 4: System Bugreport

Full system capture including `/data/anr`, `/data/tombstones`, and all system logs. Use when steps
1-3 don't provide enough context.

```bash
uv run android-emu-agent reliability bugreport --device emulator-5554
# Zip saved to ~/.android-emu-agent/artifacts/reliability
```

Use `--output` to control destination:

```bash
uv run android-emu-agent reliability bugreport --device emulator-5554 --output ./bugreport.zip
```

### Step 5: Last ANR Summary

Quick check for the most recent ANR without pulling full traces.

```bash
uv run android-emu-agent reliability last-anr --device emulator-5554
```

### Background and Process State

Check if the app is being restricted or killed by system policies.

```bash
# Background restrictions (battery optimization, app standby bucket)
uv run android-emu-agent reliability background com.example.app --device emulator-5554

# Live process snapshot (pid, oom_adj score, process state)
uv run android-emu-agent reliability process com.example.app --device emulator-5554
```

**Output interpretation for `process`:** `oom_adj` near 0 = foreground (safe). Higher values (e.g.,
900+) = cached/background (system may kill). `state` shows current scheduling state.

## Performance Diagnostics

### Memory Usage

```bash
uv run android-emu-agent reliability meminfo com.example.app --device emulator-5554
```

**Output interpretation:** Check `TOTAL PSS` for overall memory footprint. High `Native Heap` may
indicate native leaks. High `Java Heap` may indicate object retention.

### Rendering Performance

```bash
uv run android-emu-agent reliability gfxinfo com.example.app --device emulator-5554
```

**Output interpretation:** Look at frame stats — frames exceeding 16ms indicate jank. `Janky frames`
percentage shows overall smoothness.

### ART Compilation Mode

Use `--mode reset` to clear compiled code (simulates cold-start / unoptimized path). Use
`--mode speed` to force full ahead-of-time compilation (simulates optimized path).

```bash
uv run android-emu-agent reliability compile com.example.app --device emulator-5554 --mode reset
uv run android-emu-agent reliability compile com.example.app --device emulator-5554 --mode speed
```

## Rooted Devices / Emulators

### Pull Protected Artifacts (Root Required)

Direct access to system-protected directories. Faster than bugreport for targeted analysis.

```bash
uv run android-emu-agent reliability pull anr --device emulator-5554
uv run android-emu-agent reliability pull tombstones --device emulator-5554
uv run android-emu-agent reliability pull dropbox --device emulator-5554
```

### Force Thread Dump (SIGQUIT)

Use when the app is frozen/hung to capture what all threads are doing.

```bash
uv run android-emu-agent reliability sigquit com.example.app --device emulator-5554
```

### Memory Pressure Simulation

Use to test how the app handles low-memory conditions.

```bash
# Raise oom_adj to make the system more likely to kill the app
uv run android-emu-agent reliability oom-adj com.example.app --device emulator-5554 --score 1000

# Trigger the app's onTrimMemory callback at a specific level
uv run android-emu-agent reliability trim-memory com.example.app --device emulator-5554 --level RUNNING_CRITICAL
```

## Lifecycle and Scheduling Diagnostics

### Always-Finish Activities (Lifecycle Stress Test)

Forces the system to destroy activities as soon as they leave the foreground. Use to find
`onSaveInstanceState`/`onRestoreInstanceState` bugs.

```bash
uv run android-emu-agent reliability always-finish on --device emulator-5554
# ... run your test ...
uv run android-emu-agent reliability always-finish off --device emulator-5554
```

### JobScheduler Constraints

Check pending and running jobs for the app.

```bash
uv run android-emu-agent reliability jobscheduler com.example.app --device emulator-5554
```

## Debuggable App Access (No Root Needed)

These commands work on debuggable apps without root, using `run-as`.

### List App-Private Files

```bash
uv run android-emu-agent reliability run-as-ls com.example.app --device emulator-5554 --path files/
```

### Dump Heap Profile

Capture a heap dump for memory analysis.

```bash
uv run android-emu-agent reliability dumpheap com.example.app --device emulator-5554
```

Use `--keep-remote` to preserve the heap file on-device after pulling:

```bash
uv run android-emu-agent reliability dumpheap com.example.app --device emulator-5554 --keep-remote
```
