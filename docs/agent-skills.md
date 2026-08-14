# Agent Skills

Android Emu Agent ships an
[Agent Skill](https://github.com/alehkot/android-emu-agent/tree/main/skills/android-emu-agent) that
teaches a coding agent how to drive it. Installing the skill is the difference between an agent
guessing at CLI flags and an agent that follows the observe-act-verify loop correctly.

The skill tells the agent:

- which command to reach for, and when — including the selector escape hatches when a ref fails;
- how to run the observe-act-verify loop and re-snapshot after every action;
- how to recover from a failed action instead of blindly retrying;
- when to ask before write or destructive actions;
- how to triage crashes, ANRs, and performance problems, and what artifacts to collect.

The skill ships inside the Python package, so any install already has the files on disk.

## Install with the CLI

This needs no extra tooling and always matches your installed CLI version:

```bash
android-emu-agent skills install --agent claude
android-emu-agent skills install --agent codex
```

Where the files go:

| Agent                 | Command                                   | Destination                          |
| --------------------- | ----------------------------------------- | ------------------------------------ |
| Claude Code           | `skills install --agent claude`           | `~/.claude/skills/android-emu-agent` |
| Claude Code (project) | `skills install --agent claude --project` | `.claude/skills/android-emu-agent`   |
| Codex                 | `skills install --agent codex`            | `~/.codex/skills/android-emu-agent`  |
| VS Code               | `skills install --agent vscode --project` | `.agents/skills/android-emu-agent`   |
| Any other             | `skills install --dir <path>`             | `<path>/android-emu-agent`           |

`CLAUDE_CONFIG_DIR` and `CODEX_HOME` are honored when set.

Use `--project` to commit the skill alongside a repository so your team shares it. Use `--dir` for
any agent not in the table.

## Install with `npx skills`

The [skills CLI](https://github.com/vercel-labs/skills) installs from the GitHub repository and
supports many more agents:

```bash
npx skills add alehkot/android-emu-agent
```

Add `-a claude-code` to pick an agent, `-g` for a global install, and `-y` for non-interactive use.

This installs from the repository's `main` branch, so it can be newer than your installed CLI. The
built-in `skills install` always matches the CLI you have.

## Check and update

```bash
android-emu-agent skills list   # where it is installed, and which version
android-emu-agent skills path   # the bundled source directory
```

`skills install` is safe to re-run: it replaces the previous install and drops files that no longer
exist upstream. Re-run it after upgrading the CLI to refresh a copied skill.

If a skill directory exists that the CLI did not create, the command stops rather than overwrite it.
Pass `--force` to replace it.

To remove a skill, delete the directory reported by `skills list`.

## Use it

Give the agent a specific target and task:

```text
Use Android Emu Agent to open Settings on emulator-5554 and verify that Wi-Fi is enabled.
```

```text
Launch com.example.app on my emulator, sign in with test@example.com, and capture a trace if the
home screen does not appear.
```

```text
The app crashed on my device. Use Android Emu Agent to find out why and collect the evidence.
```

## Working from a source checkout

Contributors symlink the checkout's skill so edits apply immediately:

```bash
./scripts/dev.sh skills          # Codex, Claude, and this repo's .agents/skills
./scripts/dev.sh skills claude   # one target
./scripts/dev.sh skills-validate # validate skill metadata and references
```

`skills install` picks the mode automatically: a source checkout is symlinked, an installed package
is copied. Override with `--copy` or `--symlink`.

When the skill is installed from a checkout, it instructs the agent to run
`uv run android-emu-agent` so that unpublished local changes take precedence over any installed
release.
