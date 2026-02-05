# Core Loop Deep Dive

## Observe

Request a UI snapshot to see interactive elements:

```bash
uv run android-emu-agent ui snapshot <session_id>
```

The snapshot returns context and interactive elements with ephemeral `@ref` handles.

Example snapshot output:

```json
{
  "context": {
    "package": "com.example.app",
    "activity": ".MainActivity",
    "orientation": "PORTRAIT",
    "ime_visible": false
  },
  "elements": [
    {
      "ref": "@a1",
      "role": "button",
      "label": "Sign in",
      "resource_id": "com.example:id/login_btn",
      "bounds": [100, 200, 300, 250],
      "state": { "clickable": true, "enabled": true }
    }
  ]
}
```

Use `--format text` for a compact line-oriented summary. Use `--full` when you need all nodes, not
just interactive ones.

Advanced (when needed): `--raw` returns the raw XML hierarchy for low-level debugging.

## Decide

Analyze the snapshot:

- Identify the target element by `@ref`, label, or role
- Check for blockers (dialogs, overlays, loading states)
- If blocked, handle with `action back`, a targeted tap, or a wait

## Act

Execute one action at a time using the `@ref` from the current snapshot:

```bash
uv run android-emu-agent action tap <session_id> @a1
uv run android-emu-agent action set-text <session_id> @a2 "username"
uv run android-emu-agent action back <session_id>
```

Refs are ephemeral and tied to a specific snapshot generation. After any action, take a new snapshot
before acting again.

## Verify

Take a new snapshot to confirm the action had the expected effect:

```bash
uv run android-emu-agent ui snapshot <session_id>
```

Verify that the expected UI change occurred and no error dialogs appeared.

## Example Loop

```bash
# Observe
uv run android-emu-agent ui snapshot s-abc123

# Act
uv run android-emu-agent action tap s-abc123 @a1

# Verify
uv run android-emu-agent ui snapshot s-abc123
```
