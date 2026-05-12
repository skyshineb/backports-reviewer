from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path


MIGRATIONS_PACKAGE = "backport_harness.migrations"
MIGRATION_SUFFIX = ".sql"


def connect(sqlite_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with project-required pragmas enabled."""
    connection = sqlite3.connect(sqlite_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(sqlite_path) as connection:
        run_migrations(connection)


def run_migrations(connection: sqlite3.Connection) -> None:
    _ensure_schema_migrations_table(connection)

    for migration_name, migration_sql in _load_migrations():
        if _is_migration_applied(connection, migration_name):
            continue

        with connection:
            connection.executescript(migration_sql)
            connection.execute(
                """
                INSERT INTO schema_migrations(version, applied_at)
                VALUES (?, ?)
                """,
                (migration_name, _utc_now()),
            )


def _ensure_schema_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _is_migration_applied(connection: sqlite3.Connection, migration_name: str) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (migration_name,),
    )
    return cursor.fetchone() is not None


def _load_migrations() -> list[tuple[str, str]]:
    migration_files = sorted(
        resource
        for resource in resources.files(MIGRATIONS_PACKAGE).iterdir()
        if resource.name.endswith(MIGRATION_SUFFIX)
    )

    return [
        (migration_file.name, migration_file.read_text(encoding="utf-8"))
        for migration_file in migration_files
    ]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
