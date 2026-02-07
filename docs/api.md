# Daemon API Reference

Android Emu Agent exposes a FastAPI daemon over a Unix Domain Socket.

## Transport

- Socket path: `/tmp/android-emu-agent.sock`
- Base URL (with UDS clients): `http://android-emu-agent`

Example health check:

```bash
curl --unix-socket /tmp/android-emu-agent.sock \
  http://android-emu-agent/health
```

## Response Shape

Successful responses include `status: "done"`.

Errors are returned as:

```json
{
  "status": "error",
  "error": {
    "code": "ERR_*",
    "message": "...",
    "context": {},
    "remediation": "..."
  }
}
```

## New Endpoint Contracts

### `POST /artifacts/logs`

Request body:

```json
{
  "session_id": "s-abc123",
  "package": "com.example.app",
  "level": "error",
  "since": "10m",
  "follow": false
}
```

Notes:

- `session_id` is required.
- `package`, `level`, `since` are optional filters.
- `level` accepts `v|d|i|w|e|f|s` and full names like `error`, `debug`, `info`.
- `follow=true` streams logcat until client timeout.

Success response:

```json
{
  "status": "done",
  "path": "/Users/<user>/.android-agent/artifacts/s-abc123_..._logcat.txt"
}
```

### `POST /app/current`

Request body:

```json
{
  "session_id": "s-abc123"
}
```

Success response:

```json
{
  "status": "done",
  "session_id": "s-abc123",
  "package": "com.example.app",
  "activity": ".MainActivity",
  "component": "com.example.app/.MainActivity",
  "line": "mResumedActivity: ...",
  "output": "mResumedActivity: ..."
}
```

### `POST /app/task_stack`

Request body:

```json
{
  "session_id": "s-abc123"
}
```

Success response:

```json
{
  "status": "done",
  "session_id": "s-abc123",
  "output": "TASK 77 ..."
}
```

### `POST /app/resolve_intent`

Request body:

```json
{
  "session_id": "s-abc123",
  "action": "android.intent.action.VIEW",
  "data_uri": "https://example.com/deep",
  "component": null,
  "package": "com.example.app"
}
```

Notes:

- `session_id` is required.
- Provide at least one of: `action`, `data_uri`, `component`, `package`.

Success response:

```json
{
  "status": "done",
  "session_id": "s-abc123",
  "action": "android.intent.action.VIEW",
  "data_uri": "https://example.com/deep",
  "component": null,
  "package": "com.example.app",
  "resolved_component": "com.example.app/.DeepLinkActivity",
  "resolved": true,
  "output": "priority=0 ...\ncom.example.app/.DeepLinkActivity"
}
```

### `POST /reliability/process`

Request body:

```json
{
  "serial": "emulator-5554",
  "package": "com.example.app"
}
```

Notes:

- Reliability endpoints accept exactly one target: `serial` or `session_id`.

Success response:

```json
{
  "status": "done",
  "serial": "emulator-5554",
  "package": "com.example.app",
  "pid": 4321,
  "oom_score_adj": "800",
  "ps": "u0_a123 4321 ... com.example.app",
  "process_state": "...",
  "output": "PID: 4321\nOOM_SCORE_ADJ: 800\n..."
}
```

### `POST /reliability/meminfo`

Request body:

```json
{
  "serial": "emulator-5554",
  "package": "com.example.app"
}
```

Success response:

```json
{
  "status": "done",
  "serial": "emulator-5554",
  "package": "com.example.app",
  "output": "Applications Memory Usage (in Kilobytes): ..."
}
```

### `POST /reliability/gfxinfo`

Request body:

```json
{
  "serial": "emulator-5554",
  "package": "com.example.app"
}
```

Success response:

```json
{
  "status": "done",
  "serial": "emulator-5554",
  "package": "com.example.app",
  "output": "Profile data in ms: ..."
}
```
