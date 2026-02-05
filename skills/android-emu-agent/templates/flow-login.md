# Template: Login Flow

Replace placeholders like `<session_id>`, `<email>`, and `<password>`.

```bash
# Snapshot and identify fields
uv run android-emu-agent ui snapshot <session_id>
# @a1 = "Email"
# @a2 = "Password"
# @a3 = "Sign In"

# Enter email
uv run android-emu-agent action tap <session_id> @a1
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action set-text <session_id> @a1 "<email>"

# Enter password
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action tap <session_id> @a2
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action set-text <session_id> @a2 "<password>"

# Dismiss keyboard
uv run android-emu-agent action back <session_id>

# Submit
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action tap <session_id> @a3

# Verify
uv run android-emu-agent wait activity <session_id> "<HomeActivity>" --timeout-ms 15000
uv run android-emu-agent ui snapshot <session_id>
```
