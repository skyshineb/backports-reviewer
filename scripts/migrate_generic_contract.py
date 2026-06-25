#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from backport_harness.config import load_config
from backport_harness.storage import init_database


OLD_DECISIONS = (
    "DIRECT_015_BUGFIX",
    "MASTER_NOT_APPLICABLE",
    "MASTER_POSSIBLY_APPLICABLE",
    "MASTER_REPRODUCED_ON_015",
    "MASTER_FIX_VERIFIED_ON_015",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect or apply the generic-contract SQLite migration."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Harness config path. Defaults to config.yaml.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run packaged migrations for the configured SQLite database.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    sqlite_path = config.storage.sqlite_path

    if args.apply:
        init_database(sqlite_path)

    print(f"sqlite_path={sqlite_path}")
    if not sqlite_path.exists():
        print("database=missing")
        return

    with sqlite3.connect(sqlite_path) as connection:
        print("columns.prs=" + ",".join(_columns(connection, "prs")))
        print("columns.decisions=" + ",".join(_columns(connection, "decisions")))
        print("old_decisions")
        for decision, count in _old_decision_counts(connection):
            print(f"{decision}={count}")
        print("migrations")
        for version in _migrations(connection):
            print(version)


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]


def _old_decision_counts(connection: sqlite3.Connection) -> list[tuple[str, int]]:
    placeholders = ", ".join("?" for _ in OLD_DECISIONS)
    rows = connection.execute(
        f"""
        SELECT decision, COUNT(*)
        FROM decisions
        WHERE decision IN ({placeholders})
        GROUP BY decision
        ORDER BY decision
        """,
        OLD_DECISIONS,
    ).fetchall()
    return [(str(row[0]), int(row[1])) for row in rows]


def _migrations(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [str(row[0]) for row in rows]


if __name__ == "__main__":
    main()
