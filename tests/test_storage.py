from pathlib import Path

from backport_harness.storage import connect, init_database


REQUIRED_TABLES = {
    "schema_migrations",
    "prs",
    "pr_files",
    "scan_runs",
    "analysis_queue",
    "analysis_runs",
    "decisions",
    "evidence",
    "test_runs",
    "human_reviews",
}


def test_init_database_creates_file_and_parent_directory(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"

    init_database(sqlite_path)

    assert sqlite_path.is_file()


def test_init_database_creates_required_tables(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"

    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    assert REQUIRED_TABLES.issubset({row[0] for row in rows})


def test_init_database_can_be_rerun_safely(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"

    init_database(sqlite_path)
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert rows == [("001_initial.sql",)]


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert foreign_keys_enabled == 1
