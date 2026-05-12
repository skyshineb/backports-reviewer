from pathlib import Path
from typing import Optional

import typer

from backport_harness import __version__
from backport_harness.config import HarnessConfig, load_config
from backport_harness.logging_config import configure_logging
from backport_harness.storage import init_database

app = typer.Typer(help="Public upstream backport review harness.")
db_app = typer.Typer(help="Manage the harness SQLite database.")
app.add_typer(db_app, name="db")

DEFAULT_SQLITE_PATH = Path("workspace/backport_harness.sqlite3")


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


@db_app.command("init")
def db_init(ctx: typer.Context) -> None:
    """Create or update the harness SQLite database."""
    sqlite_path = _resolve_sqlite_path(ctx)
    init_database(sqlite_path)
    typer.echo(f"Initialized database at {sqlite_path}")


def _resolve_sqlite_path(ctx: typer.Context) -> Path:
    config = ctx.obj.get("config") if ctx.obj else None
    if not isinstance(config, HarnessConfig):
        return DEFAULT_SQLITE_PATH

    return config.storage.sqlite_path
