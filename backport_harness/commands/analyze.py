from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

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
    table.add_column("Branch", no_wrap=True)
    table.add_column("Merged at", no_wrap=True)
    table.add_column("Queue status", no_wrap=True)
    table.add_column("Priority", justify="right", no_wrap=True)
    table.add_column("Attempts", justify="right", no_wrap=True)
    table.add_column("Decision", no_wrap=True)
    table.add_column("Title")

    for candidate in candidates:
        table.add_row(
            f"#{candidate.github_pr_number}",
            candidate.target_branch,
            candidate.merged_at,
            candidate.queue_status,
            str(candidate.priority),
            str(candidate.attempts),
            candidate.latest_decision or "-",
            candidate.title,
        )

    console.print(table)
