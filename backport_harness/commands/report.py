from __future__ import annotations

from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backport_harness.report_writer import (
    ReportGenerationResult,
    ReportPullRequest,
    categorize_report_rows,
    filter_report_rows,
    generate_reports,
    human_review_status,
    load_report_rows,
    report_decision_confidence,
    report_decision_label,
    report_decision_reason,
    report_evidence_summary,
    report_human_action,
    report_rows_for_view,
)


REPORT_VIEWS = {"summary", "candidates", "inconclusive", "discarded", "audit"}


def write_reports(*, sqlite_path: Path, output_dir: Path) -> ReportGenerationResult:
    return generate_reports(sqlite_path=sqlite_path, output_dir=output_dir)


def render_report_view(
    *,
    sqlite_path: Path,
    view: str,
    limit: int | None = None,
    decision: str | None = None,
    queue_status: str | None = None,
    review_status: str | None = None,
    details: bool = False,
    console: Console | None = None,
) -> None:
    if view not in REPORT_VIEWS:
        allowed = ", ".join(sorted(REPORT_VIEWS))
        raise ValueError(f"view must be one of: {allowed}.")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive.")

    console = console or Console(width=220)
    rows = load_report_rows(sqlite_path)
    filtered_all_rows = filter_report_rows(
        rows,
        decision=decision,
        queue_status=queue_status,
        review_status=review_status,
        limit=limit if view == "summary" else None,
    )
    categories = categorize_report_rows(filtered_all_rows)

    if view == "summary":
        _render_summary_view(
            categories=categories,
            details=details,
            console=console,
        )
        return

    view_rows = report_rows_for_view(categories, view=view)
    view_rows = filter_report_rows(
        view_rows,
        decision=decision,
        queue_status=queue_status,
        review_status=review_status,
        limit=limit,
    )
    _render_rows_view(
        view=view,
        rows=view_rows,
        details=details,
        console=console,
    )


def _render_summary_view(
    *,
    categories,
    details: bool,
    console: Console,
) -> None:
    table = Table(title="Report Summary")
    table.add_column("Group", no_wrap=True)
    table.add_column("Rows", justify="right", no_wrap=True)
    table.add_row("audit", str(len(categories.all_rows)))
    table.add_row("candidates", str(len(categories.candidates)))
    table.add_row("inconclusive", str(len(categories.inconclusive)))
    table.add_row("discarded", str(len(categories.discarded)))
    console.print(table)

    if not details:
        return

    queue_counts = Counter(row.queue_status or "-" for row in categories.all_rows)
    decision_counts = Counter(report_decision_label(row) for row in categories.all_rows)
    review_counts = Counter(human_review_status(row) for row in categories.all_rows)

    _render_counter_table("Queue Statuses", "Queue status", queue_counts, console)
    _render_counter_table("Decisions", "Decision", decision_counts, console)
    _render_counter_table("Human Review Statuses", "Review status", review_counts, console)


def _render_counter_table(
    title: str,
    label_column: str,
    counts: Counter,
    console: Console,
) -> None:
    table = Table(title=title)
    table.add_column(label_column)
    table.add_column("Rows", justify="right", no_wrap=True)
    for label, count in sorted(counts.items()):
        table.add_row(str(label), str(count))
    if not counts:
        table.add_row("-", "0")
    console.print(table)


def _render_rows_view(
    *,
    view: str,
    rows: list[ReportPullRequest],
    details: bool,
    console: Console,
) -> None:
    title = f"Report {view.title()}"
    table = Table(title=title)
    table.add_column("PR", no_wrap=True)
    table.add_column("Upstream branch", no_wrap=True)
    table.add_column("Queue status", overflow="fold")
    table.add_column("Decision", overflow="fold")
    table.add_column("Review", overflow="fold")
    table.add_column("Merged at", no_wrap=True)
    table.add_column("Title")

    if not rows:
        table.add_row(
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "No report rows found.",
        )
        console.print(table)
        return

    for row in rows:
        values = [
            f"#{row.github_pr_number}",
            row.upstream_branch,
            row.queue_status or "-",
            report_decision_label(row),
            human_review_status(row),
            row.merged_at,
        ]
        values.append(row.title)
        table.add_row(*values)

    console.print(table)
    if details:
        _render_detail_rows(rows=rows, console=console)


def _render_detail_rows(
    *,
    rows: list[ReportPullRequest],
    console: Console,
) -> None:
    table = Table(title="Report Details")
    table.add_column("PR", no_wrap=True)
    table.add_column("Confidence", no_wrap=True)
    table.add_column("Reason", overflow="fold")
    table.add_column("Evidence", overflow="fold")
    table.add_column("Human action", overflow="fold")

    for row in rows:
        table.add_row(
            f"#{row.github_pr_number}",
            report_decision_confidence(row),
            report_decision_reason(row),
            report_evidence_summary(row.latest_decision),
            report_human_action(row),
        )

    console.print(table)
