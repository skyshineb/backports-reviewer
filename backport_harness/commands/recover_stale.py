from __future__ import annotations

from pathlib import Path

from rich.console import Console

from backport_harness.storage import connect, recover_stale_runs


def render_recover_stale(
    *,
    sqlite_path: Path,
    older_than_seconds: int,
    console: Console | None = None,
) -> int:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        console.print("Recovered 0 stale Codex run(s).")
        return 0

    with connect(sqlite_path) as connection:
        recovered = recover_stale_runs(
            connection,
            older_than_seconds=older_than_seconds,
        )

    console.print(f"Recovered {len(recovered)} stale Codex run(s).")
    return len(recovered)
