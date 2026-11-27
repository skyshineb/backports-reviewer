from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import shorten
from typing import Callable

from rich.console import Console
from rich.table import Table

from backport_harness.analysis_runner import AnalyzeBatchResult, AnalysisProgressEvent
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


def make_analysis_progress_renderer(
    console: Console | None = None,
) -> Callable[[AnalysisProgressEvent], None]:
    console = console or Console(stderr=True, width=160)

    def render(event: AnalysisProgressEvent) -> None:
        render_analysis_progress(event=event, console=console)

    return render


def render_analysis_progress(
    *,
    event: AnalysisProgressEvent,
    console: Console | None = None,
) -> None:
    console = console or Console(stderr=True, width=160)
    message = _progress_message(event)
    if message is None:
        return
    console.print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", markup=False)


def _progress_message(event: AnalysisProgressEvent) -> str | None:
    if event.event == "batch_selected":
        total = event.total if event.total is not None else 0
        return f"Selected {total} PR(s) for analysis."

    if event.event == "pr_start":
        details = [
            f"Starting {_pr_label(event)}",
            _field("branch", event.upstream_branch),
            _field("status", event.initial_queue_status),
            _field("title", _format_title(event.title)),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "run_locked":
        details = [
            f"{_pr_label(event)} run={event.run_id}",
            _attempt(event),
            _field("task", event.task_dir),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "bundle_start":
        return f"{_pr_label(event)} preparing task bundle."

    if event.event == "bundle_ready":
        return f"{_pr_label(event)} task bundle ready task={event.task_dir}"

    if event.event == "codex_start":
        details = [
            f"{_pr_label(event)} running Codex",
            _field("timeout", f"{event.timeout_seconds}s"),
            _field("stdout_log", event.stdout_log_path),
            _field("stderr_log", event.stderr_log_path),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "codex_heartbeat":
        return (
            f"{_pr_label(event)} still running Codex "
            f"elapsed={_format_elapsed(event.elapsed_seconds or 0.0)}"
        )

    if event.event == "codex_finish":
        details = [
            f"{_pr_label(event)} Codex finished",
            _field("exit", str(event.exit_code) if event.exit_code is not None else None),
            _field(
                "timed_out",
                str(event.timed_out) if event.timed_out is not None else None,
            ),
            _field("elapsed", _format_elapsed(event.elapsed_seconds or 0.0)),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "validation_start":
        return f"{_pr_label(event)} validating Codex result."

    if event.event == "validation_finish":
        details = [
            f"{_pr_label(event)} validation finished",
            _field("valid", str(event.valid)),
            _field("message", _format_error(event.error)),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "pr_finish":
        details = [
            f"Finished {_pr_label(event)}",
            _field("outcome", event.outcome),
            _field("final_status", event.final_queue_status),
            _field(
                "exit",
                str(event.exit_code) if event.exit_code is not None else None,
            ),
            _field(
                "timed_out",
                str(event.timed_out) if event.timed_out is not None else None,
            ),
            _field("message", _format_error(event.error)),
        ]
        return " ".join(detail for detail in details if detail)

    if event.event == "pr_skipped":
        details = [
            f"Skipping {_pr_label(event)}",
            _field("reason", event.skip_reason),
        ]
        return " ".join(detail for detail in details if detail)

    return None


def _pr_label(event: AnalysisProgressEvent) -> str:
    if event.pr_number is None:
        return "PR"
    label = f"PR #{event.pr_number}"
    if event.index is not None and event.total is not None:
        label = f"{label} ({event.index}/{event.total})"
    return label


def _attempt(event: AnalysisProgressEvent) -> str | None:
    if event.attempt is None:
        return None
    if event.max_attempts is None:
        return f"attempt={event.attempt}"
    return f"attempt={event.attempt}/{event.max_attempts}"


def _field(name: str, value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return f"{name}={value}"


def _format_title(title: str | None) -> str | None:
    if title is None:
        return None
    normalized = " ".join(title.split())
    return f'"{shorten(normalized, width=100, placeholder="...")}"'


def _format_error(error: str | None) -> str | None:
    if error is None:
        return None
    normalized = " ".join(error.split())
    return f'"{shorten(normalized, width=140, placeholder="...")}"'


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining_seconds = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining_seconds:.1f}s"
