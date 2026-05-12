import re
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from backport_harness import __version__
from backport_harness.config import HarnessConfig, load_config
from backport_harness.logging_config import configure_logging
from backport_harness.scanner import scan_pull_requests
from backport_harness.storage import init_database

app = typer.Typer(help="Public upstream backport review harness.")
db_app = typer.Typer(help="Manage the harness SQLite database.")
app.add_typer(db_app, name="db")

DEFAULT_SQLITE_PATH = Path("workspace/backport_harness.sqlite3")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


@app.command()
def scan(
    ctx: typer.Context,
    from_date: str = typer.Option(
        ...,
        "--from-date",
        help="Inclusive merged_at start date in YYYY-MM-DD format.",
    ),
    to_date: Optional[str] = typer.Option(
        None,
        "--to-date",
        help="Inclusive merged_at end date in YYYY-MM-DD format.",
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        help="Configured base branch to scan. Omit to scan every configured branch.",
    ),
) -> None:
    """Scan public upstream GitHub PRs into the local queue."""
    config = _require_config(ctx)
    _validate_date("from-date", from_date)
    if to_date is not None:
        _validate_date("to-date", to_date)

    try:
        summary = scan_pull_requests(
            config=config,
            sqlite_path=config.storage.sqlite_path,
            from_date=from_date,
            to_date=to_date,
            branch=branch,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(
        f"Scanned {len(summary.branches)} branch(es), "
        f"saw {summary.prs_seen} PR(s), saved {summary.prs_saved} PR(s)."
    )


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


def _require_config(ctx: typer.Context) -> HarnessConfig:
    config = ctx.obj.get("config") if ctx.obj else None
    if not isinstance(config, HarnessConfig):
        raise typer.BadParameter("A valid --config file is required for scan.")
    return config


def _validate_date(option_name: str, value: str) -> None:
    if DATE_PATTERN.fullmatch(value) is None:
        raise typer.BadParameter(f"{option_name} must use YYYY-MM-DD format.")

    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter(
            f"{option_name} must use YYYY-MM-DD format."
        ) from error
