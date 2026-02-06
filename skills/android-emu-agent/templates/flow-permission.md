# Template: Handle Runtime Permission Dialog

Replace placeholders like `<session_id>` and `<package>`.

```bash
# Launch app
uv run android-emu-agent app launch <session_id> <package>
uv run android-emu-agent wait idle <session_id> --timeout-ms 5000

# Snapshot and detect permission dialog
uv run android-emu-agent ui snapshot <session_id>
# context.package = "com.google.android.permissioncontroller"
# ^a1 = "While using the app" (or "Allow")

# Grant permission
uv run android-emu-agent action tap <session_id> ^a1
uv run android-emu-agent wait idle <session_id>

# Verify app resumed
uv run android-emu-agent ui snapshot <session_id>
# context.package = "<package>"
```
