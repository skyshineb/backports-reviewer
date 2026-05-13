from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from backport_harness.github_client import GitHubChangedFile, GitHubPullRequest


MIGRATIONS_PACKAGE = "backport_harness.migrations"
MIGRATION_SUFFIX = ".sql"
QUEUE_STATUS_QUEUED = "QUEUED_FOR_ANALYSIS"


@dataclass(frozen=True)
class SavedPullRequest:
    github_pr_number: int
    github_pr_url: str
    title: str
    target_branch: str
    merged_at: str
    queue_status: str
    priority: int
    latest_decision: str | None


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


def create_scan_run(
    connection: sqlite3.Connection,
    branch: str,
    from_date: str,
    to_date: str | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO scan_runs(branch, from_date, to_date, status, started_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (branch, from_date, to_date, "RUNNING", _utc_now()),
    )
    return int(cursor.lastrowid)


def finish_scan_run(
    connection: sqlite3.Connection,
    scan_run_id: int,
    status: str,
    prs_seen: int,
    prs_saved: int,
    last_error: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE scan_runs
        SET status = ?,
            finished_at = ?,
            prs_seen = ?,
            prs_saved = ?,
            last_error = ?
        WHERE id = ?
        """,
        (status, _utc_now(), prs_seen, prs_saved, last_error, scan_run_id),
    )


def upsert_pull_request(
    connection: sqlite3.Connection,
    pull_request: GitHubPullRequest,
) -> int:
    now = _utc_now()
    connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            body,
            source_branch,
            target_branch,
            merged_commit_sha,
            created_at,
            updated_at,
            closed_at,
            merged_at,
            author,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(github_pr_number, target_branch) DO UPDATE SET
            github_pr_url = excluded.github_pr_url,
            title = excluded.title,
            body = excluded.body,
            source_branch = excluded.source_branch,
            merged_commit_sha = excluded.merged_commit_sha,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            closed_at = excluded.closed_at,
            merged_at = excluded.merged_at,
            author = excluded.author,
            updated_in_db_at = excluded.updated_in_db_at
        """,
        (
            pull_request.number,
            pull_request.html_url,
            pull_request.title,
            pull_request.body,
            pull_request.head_ref,
            pull_request.base_ref,
            pull_request.merge_commit_sha,
            pull_request.created_at,
            pull_request.updated_at,
            pull_request.closed_at,
            pull_request.merged_at,
            pull_request.author,
            now,
            now,
        ),
    )
    cursor = connection.execute(
        """
        SELECT id
        FROM prs
        WHERE github_pr_number = ? AND target_branch = ?
        """,
        (pull_request.number, pull_request.base_ref),
    )
    return int(cursor.fetchone()[0])


def replace_pull_request_files(
    connection: sqlite3.Connection,
    pr_id: int,
    files: list[GitHubChangedFile],
) -> None:
    connection.execute("DELETE FROM pr_files WHERE pr_id = ?", (pr_id,))
    connection.executemany(
        """
        INSERT INTO pr_files(
            pr_id,
            filename,
            status,
            additions,
            deletions,
            is_test_file,
            is_docs_file,
            is_ci_file
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                pr_id,
                changed_file.filename,
                changed_file.status,
                changed_file.additions,
                changed_file.deletions,
                int(is_test_file(changed_file.filename)),
                int(is_docs_file(changed_file.filename)),
                int(is_ci_file(changed_file.filename)),
            )
            for changed_file in files
        ],
    )


def create_analysis_queue_row_if_missing(
    connection: sqlite3.Connection,
    pr_id: int,
) -> None:
    now = _utc_now()
    connection.execute(
        """
        INSERT OR IGNORE INTO analysis_queue(
            pr_id,
            status,
            priority,
            attempts,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pr_id, QUEUE_STATUS_QUEUED, 100, 0, now, now),
    )


def list_saved_pull_requests(
    connection: sqlite3.Connection,
    *,
    branch: str | None = None,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int | None = None,
    order_by: str = "merged-at",
) -> list[SavedPullRequest]:
    where_clauses = []
    parameters: list[object] = []

    if branch is not None:
        where_clauses.append("prs.target_branch = ?")
        parameters.append(branch)

    if status is not None:
        where_clauses.append("analysis_queue.status = ?")
        parameters.append(status)

    if from_date is not None:
        where_clauses.append("prs.merged_at >= ?")
        parameters.append(f"{from_date}T00:00:00Z")

    if to_date is not None:
        where_clauses.append("prs.merged_at <= ?")
        parameters.append(f"{to_date}T23:59:59Z")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    order_sql = {
        "merged-at": "prs.merged_at ASC",
        "branch": "prs.target_branch ASC, prs.merged_at ASC",
        "priority": "analysis_queue.priority ASC, prs.merged_at ASC",
        "status": "analysis_queue.status ASC, prs.merged_at ASC",
    }[order_by]

    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ?"
        parameters.append(limit)

    cursor = connection.execute(
        f"""
        WITH latest_decisions AS (
            SELECT ranked.pr_id, ranked.decision
            FROM (
                SELECT
                    decisions.pr_id,
                    decisions.decision,
                    ROW_NUMBER() OVER (
                        PARTITION BY decisions.pr_id
                        ORDER BY decisions.created_at DESC, decisions.id DESC
                    ) AS row_number
                FROM decisions
            ) AS ranked
            WHERE ranked.row_number = 1
        )
        SELECT
            prs.github_pr_number,
            prs.github_pr_url,
            prs.title,
            prs.target_branch,
            prs.merged_at,
            analysis_queue.status,
            analysis_queue.priority,
            latest_decisions.decision
        FROM prs
        JOIN analysis_queue ON analysis_queue.pr_id = prs.id
        LEFT JOIN latest_decisions ON latest_decisions.pr_id = prs.id
        {where_sql}
        ORDER BY {order_sql}
        {limit_sql}
        """,
        parameters,
    )

    return [
        SavedPullRequest(
            github_pr_number=int(row[0]),
            github_pr_url=str(row[1]),
            title=str(row[2]),
            target_branch=str(row[3]),
            merged_at=str(row[4]),
            queue_status=str(row[5]),
            priority=int(row[6]),
            latest_decision=row[7],
        )
        for row in cursor.fetchall()
    ]


def is_test_file(filename: str) -> bool:
    normalized = filename.lower()
    name = Path(normalized).name
    return (
        "/test/" in f"/{normalized}/"
        or "/tests/" in f"/{normalized}/"
        or normalized.startswith("src/test/")
        or name.startswith("test_")
        or "_test." in name
    )


def is_docs_file(filename: str) -> bool:
    normalized = filename.lower()
    return (
        normalized.startswith("docs/")
        or normalized.endswith(".md")
        or normalized.endswith(".rst")
    )


def is_ci_file(filename: str) -> bool:
    normalized = filename.lower()
    name = Path(normalized).name
    return (
        normalized.startswith(".github/")
        or normalized.startswith(".circleci/")
        or normalized.startswith("ci/")
        or name == "jenkinsfile"
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
