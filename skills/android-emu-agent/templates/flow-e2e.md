# Template: Full E2E Flow

Replace placeholders like `<session_id>`, `<package>`, `<email>`, and `<password>`.

```bash
# Start session
uv run android-emu-agent session start --device <serial>
# session_id = <session_id>

# Reset and launch
uv run android-emu-agent app reset <session_id> <package>
uv run android-emu-agent app launch <session_id> <package>
uv run android-emu-agent wait idle <session_id> --timeout-ms 10000

# Onboarding (tap Skip if present)
uv run android-emu-agent ui snapshot <session_id>
# @a1 = "Skip"
uv run android-emu-agent action tap <session_id> @a1
uv run android-emu-agent wait idle <session_id>

# Login
uv run android-emu-agent ui snapshot <session_id>
# @a2 = "Email", @a3 = "Password", @a4 = "Login"

uv run android-emu-agent action tap <session_id> @a2
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action set-text <session_id> @a2 "<email>"

uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action tap <session_id> @a3
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action set-text <session_id> @a3 "<password>"

uv run android-emu-agent action back <session_id>
uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action tap <session_id> @a4

# Verify home
uv run android-emu-agent wait activity <session_id> "<HomeActivity>" --timeout-ms 15000
uv run android-emu-agent ui snapshot <session_id>

# Capture artifacts
uv run android-emu-agent artifact screenshot <session_id>
uv run android-emu-agent artifact logs <session_id>

# Cleanup
uv run android-emu-agent session stop <session_id>
```
