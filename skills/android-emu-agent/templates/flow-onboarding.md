# Template: Skip Onboarding

Replace placeholders like `<session_id>`.

Option A: Tap "Skip"

```bash
uv run android-emu-agent ui snapshot <session_id>
# ^a1 = "Skip"
uv run android-emu-agent action tap <session_id> ^a1
uv run android-emu-agent wait idle <session_id>
```

Option B: Tap through "Next" pages

```bash
uv run android-emu-agent ui snapshot <session_id>
# ^a1 = "Next"
uv run android-emu-agent action tap <session_id> ^a1
uv run android-emu-agent wait idle <session_id>

uv run android-emu-agent ui snapshot <session_id>
uv run android-emu-agent action tap <session_id> ^a1
uv run android-emu-agent wait idle <session_id>

uv run android-emu-agent ui snapshot <session_id>
# ^a2 = "Get Started"
uv run android-emu-agent action tap <session_id> ^a2
```

Option C: Swipe carousel

```bash
uv run android-emu-agent action swipe left -s <session_id>
uv run android-emu-agent wait idle <session_id>

uv run android-emu-agent action swipe left -s <session_id>
uv run android-emu-agent wait idle <session_id>

uv run android-emu-agent action swipe left -s <session_id>
uv run android-emu-agent wait idle <session_id>

uv run android-emu-agent ui snapshot <session_id>
# ^a1 = "Done" or "Get Started"
uv run android-emu-agent action tap <session_id> ^a1
```
