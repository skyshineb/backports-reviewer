from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from backport_harness.storage import connect, list_saved_pull_requests


VALID_ORDER_BY = {"merged-at", "branch", "priority", "status"}


def render_list_prs(
    *,
    sqlite_path: Path,
    branch: str | None,
    status: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int | None,
    order_by: str,
    console: Console | None = None,
) -> None:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        console.print("No saved PRs found.")
        return

    with connect(sqlite_path) as connection:
        pull_requests = list_saved_pull_requests(
            connection,
            branch=branch,
            status=status,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            order_by=order_by,
        )

    if not pull_requests:
        console.print("No saved PRs found.")
        return

    table = Table()
    table.add_column("PR", no_wrap=True)
    table.add_column("Branch", no_wrap=True)
    table.add_column("Merged at", no_wrap=True)
    table.add_column("Queue status", no_wrap=True)
    table.add_column("Priority", justify="right", no_wrap=True)
    table.add_column("Decision", no_wrap=True)
    table.add_column("Title")

    for pull_request in pull_requests:
        table.add_row(
            f"#{pull_request.github_pr_number}",
            pull_request.target_branch,
            pull_request.merged_at,
            pull_request.queue_status,
            str(pull_request.priority),
            pull_request.latest_decision or "-",
            pull_request.title,
        )

    console.print(table)
