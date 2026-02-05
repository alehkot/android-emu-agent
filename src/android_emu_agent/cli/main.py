"""CLI entry point using Typer."""

from __future__ import annotations

import typer

from android_emu_agent.cli.commands import (
    action,
    app_cmd,
    artifact,
    daemon,
    device,
    emulator,
    reliability,
    session,
    ui,
    wait,
)
from android_emu_agent.cli.commands import (
    file as file_commands,
)

app = typer.Typer(
    name="android-emu-agent",
    help="LLM-driven Android UI control system",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show version information."""
    from android_emu_agent import __version__

    typer.echo(f"android-emu-agent v{__version__}")


app.add_typer(daemon.app, name="daemon")
app.add_typer(device.app, name="device")
app.add_typer(session.app, name="session")
app.add_typer(ui.app, name="ui")
app.add_typer(action.app, name="action")
app.add_typer(wait.app, name="wait")
app.add_typer(app_cmd.app, name="app")
app.add_typer(artifact.app, name="artifact")
app.add_typer(emulator.app, name="emulator")
app.add_typer(reliability.app, name="reliability")
app.add_typer(file_commands.app, name="file")


if __name__ == "__main__":
    app()
