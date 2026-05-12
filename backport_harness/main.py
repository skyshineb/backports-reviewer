from pathlib import Path
from typing import Optional

import typer

from backport_harness import __version__
from backport_harness.config import load_config
from backport_harness.logging_config import configure_logging

app = typer.Typer(help="Public upstream backport review harness.")


@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        Path("config.yaml"),
        "--config",
        "-c",
        help="Path to the harness YAML config file.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging.",
    ),
) -> None:
    configure_logging(verbose=verbose)
    ctx.obj = {"config_path": config, "config": None}

    if config and config.exists():
        ctx.obj["config"] = load_config(config)


@app.command()
def version() -> None:
    """Print the backport harness version."""
    typer.echo(__version__)

