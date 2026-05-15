from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from backport_harness.storage import connect, store_human_review


@dataclass(frozen=True)
class ReviewCommandResult:
    pr_number: int
    status: str


def render_review(
    *,
    sqlite_path: Path,
    pr_number: int,
    status: str,
    comment: str | None = None,
    console: Console | None = None,
) -> ReviewCommandResult:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        raise ValueError(f"No saved PR found for #{pr_number}.")

    with connect(sqlite_path) as connection:
        store_human_review(
            connection,
            pr_number=pr_number,
            status=status,
            comment=comment,
        )

    console.print(f"Recorded human review for #{pr_number}: {status}")
    return ReviewCommandResult(pr_number=pr_number, status=status)
