# Workflow Examples

> **Read this file when** you need examples for visual grounding, trace archives, capability-guided
> selector planning, intent preflight, or evidence bundles.

These examples assume an active session named `s-abc123` and app package `com.example.app`.

## Visual Grounding

```bash
uv run android-emu-agent ui snapshot s-abc123 --format text
uv run android-emu-agent ui snapshot s-abc123 --full
uv run android-emu-agent ui ground s-abc123 --ref ^a1 --ref ^a4 --pull --output ./artifacts/grounding.json --json
uv run android-emu-agent ui screenshot s-abc123 --pull --output ./artifacts/screen.png --json
```

Use the grounding JSON `bounds` and `center` fields to connect refs to screenshot coordinates. Run a
fresh snapshot first; `ui ground` uses refs from the latest generation.

## Trace Archive for a Flaky Flow

```bash
uv run android-emu-agent trace start s-abc123 --label checkout-flake
uv run android-emu-agent ui snapshot s-abc123 --format text
uv run android-emu-agent action tap s-abc123 'text:"Checkout" || id:com.example:id/checkout'
uv run android-emu-agent wait exists s-abc123 --text "Payment" --timeout-ms 5000
uv run android-emu-agent expect activity s-abc123 CheckoutActivity --timeout-ms 5000
uv run android-emu-agent trace stop s-abc123 --output ./artifacts/checkout-flake.aea-trace.zip
uv run android-emu-agent trace replay ./artifacts/checkout-flake.aea-trace.zip --until-failure
uv run android-emu-agent trace export ./artifacts/checkout-flake.aea-trace.zip --output ./artifacts/checkout-flake.md
```

Replay is a dry-run plan. Attach the `.aea-trace.zip`, exported Markdown, and any screenshots/logs
from the same run.

## Capability-Guided Selector Planning

```bash
uv run android-emu-agent device capabilities --session s-abc123 --json
uv run android-emu-agent action tap s-abc123 'text:"Sign in" || id:com.example:id/sign_in'
uv run android-emu-agent action tap s-abc123 'text:"Continue" enabled:true clickable:true'
uv run android-emu-agent ui screenshot s-abc123 --pull --output ./artifacts/continue.png
uv run android-emu-agent action tap s-abc123 coords:540,1820
```

Use semantic selectors first. Only fall back to coordinates when the capability report and
screenshot make the coordinate target safe.

## Intent and Deep-Link Preflight

```bash
uv run android-emu-agent app resolve-intent --session s-abc123 --action android.intent.action.VIEW --data "https://example.com/deep" --json
uv run android-emu-agent app deeplink s-abc123 "https://example.com/deep"
uv run android-emu-agent wait activity s-abc123 DeepLinkActivity --timeout-ms 10000
uv run android-emu-agent app intent s-abc123 --action android.intent.action.VIEW --data "https://example.com/deep" --package com.example.app
uv run android-emu-agent app intent s-abc123 --action android.intent.action.VIEW --data "https://example.com/deep" --package com.example.app --wait-debugger
uv run android-emu-agent debug attach --session s-abc123 --package com.example.app --keep-suspended
```

Resolve first when multiple apps may handle a URI. Use `--component com.example.app/.Activity` for
known explicit screens.

## Evidence Bundle After a Failed Flow

```bash
uv run android-emu-agent artifact save-snapshot s-abc123 --json
uv run android-emu-agent artifact screenshot s-abc123 --pull --output ./artifacts/failure-screen.png --json
uv run android-emu-agent artifact logs --session s-abc123 --app com.example.app --type errors --since "10m ago" --json
uv run android-emu-agent app current --session s-abc123 --json
uv run android-emu-agent app task-stack --session s-abc123 --json
uv run android-emu-agent artifact bundle s-abc123 --json
```

If the failure looks like a crash or ANR, continue with `references/reliability.md`.
