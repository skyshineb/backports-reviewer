from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from backport_harness.analysis_runner import AnalyzeBatchResult
from backport_harness.storage import connect, select_analysis_candidates


def render_analyze_dry_run(
    *,
    sqlite_path: Path,
    limit: int,
    console: Console | None = None,
) -> None:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        console.print("No analysis candidates found.")
        return

    with connect(sqlite_path) as connection:
        candidates = select_analysis_candidates(connection, limit=limit)

    if not candidates:
        console.print("No analysis candidates found.")
        return

    table = Table(title="Analysis Dry Run")
    table.add_column("PR", no_wrap=True)
    table.add_column("Upstream branch", no_wrap=True)
    table.add_column("Merged at", no_wrap=True)
    table.add_column("Queue status", no_wrap=True)
    table.add_column("Priority", justify="right", no_wrap=True)
    table.add_column("Attempts", justify="right", no_wrap=True)
    table.add_column("Decision", no_wrap=True)
    table.add_column("Title")

    for candidate in candidates:
        table.add_row(
            f"#{candidate.github_pr_number}",
            candidate.upstream_branch,
            candidate.merged_at,
            candidate.queue_status,
            str(candidate.priority),
            str(candidate.attempts),
            candidate.latest_decision or "-",
            candidate.title,
        )

    console.print(table)


def render_analyze_batch_summary(
    *,
    result: AnalyzeBatchResult,
    console: Console | None = None,
) -> None:
    console = console or Console(width=160)

    summary = Table(title="Analysis Batch Summary")
    summary.add_column("Selected", justify="right", no_wrap=True)
    summary.add_column("Processed", justify="right", no_wrap=True)
    summary.add_column("Succeeded", justify="right", no_wrap=True)
    summary.add_column("Failures", justify="right", no_wrap=True)
    summary.add_column("Skipped", justify="right", no_wrap=True)
    summary.add_column("Elapsed", no_wrap=True)
    summary.add_column("Stop reason")
    summary.add_row(
        str(result.selected_count),
        str(result.processed_count),
        str(result.succeeded_count),
        str(result.failed_count),
        str(result.skipped_count),
        _format_elapsed(result.elapsed_seconds),
        result.stop_reason,
    )
    console.print(summary)

    if not result.items:
        console.print("No analysis candidates found.")
        return

    rows = Table(title="Selected PRs")
    rows.add_column("PR", no_wrap=True)
    rows.add_column("Outcome", no_wrap=True)
    rows.add_column("Upstream branch", no_wrap=True)
    rows.add_column("Initial status", no_wrap=True)
    rows.add_column("Final status", no_wrap=True)
    rows.add_column("Run", no_wrap=True)
    rows.add_column("Exit", justify="right", no_wrap=True)
    rows.add_column("Timed out", no_wrap=True)
    rows.add_column("Message")
    rows.add_column("Title")

    for item in result.items:
        rows.add_row(
            f"#{item.pr_number}",
            item.outcome,
            item.upstream_branch,
            item.initial_queue_status,
            item.final_queue_status or "-",
            item.run_id or "-",
            str(item.codex_exit_code) if item.codex_exit_code is not None else "-",
            str(item.timed_out) if item.timed_out is not None else "-",
            item.error or item.skip_reason or "-",
            item.title,
        )

    console.print(rows)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining_seconds = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining_seconds:.1f}s"
