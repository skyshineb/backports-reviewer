import re
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from backport_harness import __version__
from backport_harness.analysis_runner import analyze_one_pr
from backport_harness.commands.analyze import render_analyze_dry_run
from backport_harness.commands.inspect_pr import render_inspect_pr
from backport_harness.commands.list_prs import VALID_ORDER_BY, render_list_prs
from backport_harness.commands.recover_stale import render_recover_stale
from backport_harness.commands.report import write_reports
from backport_harness.commands.review import render_review
from backport_harness.commands.retry import render_retry
from backport_harness.config import DEFAULT_ANALYSIS_LIMIT
from backport_harness.config import HarnessConfig, load_config
from backport_harness.logging_config import configure_logging
from backport_harness.scanner import scan_pull_requests
from backport_harness.state_machine import (
    QUEUE_STATUS_FAILED_INFRA,
    QUEUE_STATUS_NEEDS_RETRY,
)
from backport_harness.storage import HUMAN_REVIEW_STATUSES, init_database
from backport_harness.task_builder import build_task_bundle
from backport_harness.worktree_manager import prepare_target_worktree

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
    pr: Optional[int] = typer.Option(
        None,
        "--pr",
        help="GitHub PR number to analyze with Codex.",
    ),
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
    if pr is not None and pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")
    if pr is not None and dry_run:
        raise typer.BadParameter("--pr cannot be combined with --dry-run.")

    if pr is not None:
        config = _require_config(ctx)
        try:
            result = analyze_one_pr(config=config, pr_number=pr)
        except (RuntimeError, ValueError) as error:
            raise typer.BadParameter(str(error)) from error

        typer.echo(
            f"Analyzed PR #{pr} in run {result.run_id}; "
            f"exit={result.codex_result.exit_code}, "
            f"timed_out={result.codex_result.timed_out}."
        )
        return

    if not dry_run:
        raise typer.BadParameter("Use --dry-run or --pr.")

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
        help="GitHub PR number to prepare a configured public target-ref worktree for.",
    ),
) -> None:
    """Prepare a configured public target-ref worktree for one PR."""
    if pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")

    config = _require_config(ctx)
    try:
        worktree_path = prepare_target_worktree(config, pr_number=pr)
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


@app.command("report")
def report(ctx: typer.Context) -> None:
    """Generate review reports from the local SQLite database."""
    config = _require_config(ctx)
    result = write_reports(
        sqlite_path=config.storage.sqlite_path,
        output_dir=config.reports.output_dir,
    )

    typer.echo(f"Generated reports in {result.output_dir}")
    typer.echo(
        f"- {result.backport_candidates_path}: "
        f"{result.backport_candidates_count} row(s)"
    )
    typer.echo(f"- {result.inconclusive_path}: {result.inconclusive_count} row(s)")
    typer.echo(f"- {result.discarded_path}: {result.discarded_count} row(s)")
    typer.echo(f"- {result.full_audit_path}: {result.full_audit_count} row(s)")


@app.command("review")
def review(
    ctx: typer.Context,
    pr: int = typer.Option(
        ...,
        "--pr",
        help="GitHub PR number to mark with a human review status.",
    ),
    status: str = typer.Option(
        ...,
        "--status",
        help="Human review status to record.",
    ),
    comment: Optional[str] = typer.Option(
        None,
        "--comment",
        help="Optional human review comment.",
    ),
) -> None:
    """Record a human review status for one saved PR."""
    if pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")
    if status not in HUMAN_REVIEW_STATUSES:
        allowed = ", ".join(sorted(HUMAN_REVIEW_STATUSES))
        raise typer.BadParameter(f"status must be one of: {allowed}.")

    try:
        render_review(
            sqlite_path=_resolve_sqlite_path(ctx),
            pr_number=pr,
            status=status,
            comment=comment,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


@app.command("recover-stale")
def recover_stale(
    ctx: typer.Context,
    older_than_hours: Optional[float] = typer.Option(
        None,
        "--older-than-hours",
        help="Recover CODEX_RUNNING rows locked longer than this many hours.",
    ),
) -> None:
    """Mark stale Codex analysis runs retryable."""
    config = _require_config(ctx)
    if older_than_hours is not None:
        if older_than_hours <= 0:
            raise typer.BadParameter("older-than-hours must be positive.")
        older_than_seconds = int(older_than_hours * 3600)
    else:
        older_than_seconds = config.analysis.stale_timeout_seconds

    if older_than_seconds <= 0:
        raise typer.BadParameter("stale timeout must be positive.")

    render_recover_stale(
        sqlite_path=config.storage.sqlite_path,
        older_than_seconds=older_than_seconds,
    )


@app.command("retry")
def retry(
    ctx: typer.Context,
    pr: Optional[int] = typer.Option(
        None,
        "--pr",
        help="GitHub PR number to queue for another analysis attempt.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Queue status to bulk retry: NEEDS_RETRY or FAILED_INFRA.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum number of PRs to retry by status.",
    ),
) -> None:
    """Queue selected PRs for another analysis attempt."""
    if (pr is None) == (status is None):
        raise typer.BadParameter("Exactly one selector is required: --pr or --status.")
    if pr is not None and pr < 1:
        raise typer.BadParameter("pr must be a positive integer.")
    if limit is not None and limit < 1:
        raise typer.BadParameter("limit must be a positive integer.")
    if pr is not None and limit is not None:
        raise typer.BadParameter("--limit cannot be combined with --pr.")
    if status is not None and status not in {
        QUEUE_STATUS_NEEDS_RETRY,
        QUEUE_STATUS_FAILED_INFRA,
    }:
        raise typer.BadParameter(
            "Bulk retry supports only NEEDS_RETRY or FAILED_INFRA. "
            "Use --pr to retry an INCONCLUSIVE decision."
        )

    config = _require_config(ctx)
    resolved_limit = limit if limit is not None else config.analysis.default_limit
    try:
        render_retry(
            sqlite_path=config.storage.sqlite_path,
            max_attempts=config.codex.max_attempts_per_pr,
            pr_number=pr,
            status=status,
            limit=resolved_limit if status is not None else None,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


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
        raise typer.BadParameter("A valid --config file is required for this command.")
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
