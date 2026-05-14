import re
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from backport_harness import __version__
from backport_harness.commands.analyze import render_analyze_dry_run
from backport_harness.commands.inspect_pr import render_inspect_pr
from backport_harness.commands.list_prs import VALID_ORDER_BY, render_list_prs
from backport_harness.config import DEFAULT_ANALYSIS_LIMIT
from backport_harness.config import HarnessConfig, load_config
from backport_harness.logging_config import configure_logging
from backport_harness.scanner import scan_pull_requests
from backport_harness.storage import init_database
from backport_harness.task_builder import build_task_bundle
from backport_harness.worktree_manager import prepare_oss_015_worktree

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


@app.command("list-prs")
def list_prs(
    ctx: typer.Context,
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        help="Saved PR target branch to display.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Analysis queue status to display.",
    ),
    from_date: Optional[str] = typer.Option(
        None,
        "--from-date",
        help="Inclusive merged_at start date in YYYY-MM-DD format.",
    ),
    to_date: Optional[str] = typer.Option(
        None,
        "--to-date",
        help="Inclusive merged_at end date in YYYY-MM-DD format.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum number of PRs to display.",
    ),
    order_by: str = typer.Option(
        "merged-at",
        "--order-by",
        help="Ordering: merged-at, branch, priority, or status.",
    ),
) -> None:
    """List saved PRs from the local SQLite database."""
    if from_date is not None:
        _validate_date("from-date", from_date)
    if to_date is not None:
        _validate_date("to-date", to_date)
    if limit is not None and limit < 1:
        raise typer.BadParameter("limit must be a positive integer.")
    if order_by not in VALID_ORDER_BY:
        raise typer.BadParameter(
            "order-by must be one of: branch, merged-at, priority, status."
        )

    render_list_prs(
        sqlite_path=_resolve_sqlite_path(ctx),
        branch=branch,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        order_by=order_by,
    )


@app.command("inspect")
def inspect(
    ctx: typer.Context,
    pr: int = typer.Option(
        ...,
        "--pr",
        help="GitHub PR number to inspect.",
    ),
) -> None:
    """Inspect one saved PR from the local SQLite database."""
    if pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")

    render_inspect_pr(sqlite_path=_resolve_sqlite_path(ctx), pr_number=pr)


@app.command("analyze")
def analyze(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum number of queued PRs to select.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show selected PRs without invoking Codex.",
    ),
) -> None:
    """Plan analysis candidates from the local SQLite queue."""
    if not dry_run:
        raise typer.BadParameter("Codex analysis is not implemented yet; use --dry-run.")

    resolved_limit = _resolve_analysis_limit(ctx) if limit is None else limit
    if resolved_limit < 1:
        raise typer.BadParameter("limit must be a positive integer.")

    render_analyze_dry_run(
        sqlite_path=_resolve_sqlite_path(ctx),
        limit=resolved_limit,
    )


@app.command("prepare")
def prepare(
    ctx: typer.Context,
    pr: int = typer.Option(
        ...,
        "--pr",
        help="GitHub PR number to prepare a public OSS 0.15 worktree for.",
    ),
) -> None:
    """Prepare a public OSS 0.15 worktree for one PR."""
    if pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")

    config = _require_config(ctx)
    try:
        worktree_path = prepare_oss_015_worktree(config, pr_number=pr)
    except (RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Prepared worktree at {worktree_path}")


@app.command("prepare-bundle")
def prepare_bundle(
    ctx: typer.Context,
    pr: int = typer.Option(
        ...,
        "--pr",
        help="GitHub PR number to prepare a public Codex task bundle for.",
    ),
) -> None:
    """Prepare a public Codex task bundle for one saved PR."""
    if pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")

    config = _require_config(ctx)
    try:
        bundle = build_task_bundle(
            config=config,
            sqlite_path=config.storage.sqlite_path,
            pr_number=pr,
        )
    except (RuntimeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(f"Prepared task bundle at {bundle.task_dir}")


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


def _resolve_analysis_limit(ctx: typer.Context) -> int:
    config = ctx.obj.get("config") if ctx.obj else None
    if not isinstance(config, HarnessConfig):
        return DEFAULT_ANALYSIS_LIMIT

    return config.analysis.default_limit


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
