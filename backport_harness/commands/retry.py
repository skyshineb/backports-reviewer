from __future__ import annotations

from pathlib import Path

from rich.console import Console

from backport_harness.storage import connect, retry_pull_requests


def render_retry(
    *,
    sqlite_path: Path,
    max_attempts: int,
    pr_number: int | None = None,
    status: str | None = None,
    limit: int | None = None,
    console: Console | None = None,
) -> int:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        console.print("Retried 0 PR(s).")
        return 0

    with connect(sqlite_path) as connection:
        result = retry_pull_requests(
            connection,
            max_attempts=max_attempts,
            pr_number=pr_number,
            status=status,
            limit=limit,
        )

    console.print(f"Retried {len(result.retried)} PR(s).")
    if result.skipped:
        console.print(f"Skipped {len(result.skipped)} PR(s).")
        for skipped in result.skipped:
            console.print(f"- #{skipped.github_pr_number}: {skipped.reason}")

    return len(result.retried)
