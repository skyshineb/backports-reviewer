from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from backport_harness.codex_result import CodexResult, Decision
from backport_harness.github_client import GitHubChangedFile, GitHubPullRequest
from backport_harness.state_machine import (
    QUEUE_STATUS_DONE,
    QUEUE_STATUS_FAILED_INFRA,
    QUEUE_STATUS_NEEDS_RETRY,
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_REPORTABLE,
    QUEUE_STATUS_RUNNING,
    QUEUE_STATUS_VALIDATED,
    RETRYABLE_QUEUE_STATUSES,
    assign_initial_priority,
)


MIGRATIONS_PACKAGE = "backport_harness.migrations"
MIGRATION_SUFFIX = ".sql"


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


@dataclass(frozen=True)
class AnalysisCandidate:
    github_pr_number: int
    github_pr_url: str
    title: str
    target_branch: str
    merged_at: str
    queue_status: str
    priority: int
    attempts: int
    latest_decision: str | None


@dataclass(frozen=True)
class AnalysisStart:
    pr_id: int
    analysis_run_id: int
    run_id: str
    attempts: int


@dataclass(frozen=True)
class InspectedPullRequestFile:
    filename: str
    status: str | None
    additions: int | None
    deletions: int | None
    is_test_file: bool
    is_docs_file: bool
    is_ci_file: bool


@dataclass(frozen=True)
class InspectedQueueState:
    status: str
    priority: int
    attempts: int
    next_retry_at: str | None
    locked_at: str | None
    locked_by: str | None
    last_error: str | None


@dataclass(frozen=True)
class InspectedAnalysisRun:
    id: int
    run_id: str
    started_at: str
    finished_at: str | None
    codex_exit_code: int | None
    status: str
    task_dir: str
    result_json_path: str | None
    notes_path: str | None
    stdout_log_path: str | None
    stderr_log_path: str | None


@dataclass(frozen=True)
class InspectedDecision:
    decision: str
    confidence: str
    bugfix_classification: str | None
    applies_to_oss_015: bool | None
    reason: str
    human_action: str | None
    created_at: str
    analysis_run: InspectedAnalysisRun


@dataclass(frozen=True)
class InspectedEvidence:
    evidence_type: str
    description: str
    file_path: str | None
    command: str | None
    exit_code: int | None
    log_path: str | None


@dataclass(frozen=True)
class InspectedTestRun:
    phase: str
    command: str | None
    exit_code: int | None
    result: str
    log_path: str | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class InspectedHumanReview:
    status: str
    reviewer: str | None
    comment: str | None
    updated_at: str


@dataclass(frozen=True)
class InspectedPullRequest:
    github_pr_number: int
    github_pr_url: str
    title: str
    body: str | None
    source_branch: str | None
    target_branch: str
    merged_commit_sha: str | None
    created_at: str | None
    updated_at: str | None
    closed_at: str | None
    merged_at: str
    author: str | None
    queue: InspectedQueueState | None
    files: list[InspectedPullRequestFile]
    latest_analysis_run: InspectedAnalysisRun | None
    latest_decision: InspectedDecision | None
    evidence: list[InspectedEvidence]
    test_runs: list[InspectedTestRun]
    human_review: InspectedHumanReview | None


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
    *,
    target_branch: str,
    title: str,
) -> None:
    now = _utc_now()
    priority = assign_initial_priority(target_branch=target_branch, title=title)
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
        (pr_id, QUEUE_STATUS_QUEUED, priority, 0, now, now),
    )


def select_analysis_candidates(
    connection: sqlite3.Connection,
    *,
    limit: int,
) -> list[AnalysisCandidate]:
    retryable_statuses = sorted(RETRYABLE_QUEUE_STATUSES)
    placeholders = ", ".join("?" for _ in retryable_statuses)
    parameters: list[object] = [*retryable_statuses, limit]

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
            analysis_queue.attempts,
            latest_decisions.decision
        FROM analysis_queue
        JOIN prs ON prs.id = analysis_queue.pr_id
        LEFT JOIN latest_decisions ON latest_decisions.pr_id = prs.id
        WHERE analysis_queue.status IN ({placeholders})
        ORDER BY analysis_queue.priority ASC,
                 prs.merged_at ASC,
                 analysis_queue.id ASC
        LIMIT ?
        """,
        parameters,
    )

    return [
        AnalysisCandidate(
            github_pr_number=int(row[0]),
            github_pr_url=str(row[1]),
            title=str(row[2]),
            target_branch=str(row[3]),
            merged_at=str(row[4]),
            queue_status=str(row[5]),
            priority=int(row[6]),
            attempts=int(row[7]),
            latest_decision=row[8],
        )
        for row in cursor.fetchall()
    ]


def start_analysis_run(
    connection: sqlite3.Connection,
    *,
    pr_number: int,
    run_id: str,
    task_dir: Path,
    locked_by: str,
) -> AnalysisStart:
    now = _utc_now()
    row = connection.execute(
        """
        SELECT prs.id, analysis_queue.status, analysis_queue.attempts
        FROM prs
        JOIN analysis_queue ON analysis_queue.pr_id = prs.id
        WHERE prs.github_pr_number = ?
        ORDER BY prs.target_branch ASC
        LIMIT 1
        """,
        (pr_number,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No queued saved PR found for #{pr_number}.")

    pr_id = int(row[0])
    status = str(row[1])
    attempts = int(row[2]) + 1
    if status not in RETRYABLE_QUEUE_STATUSES:
        raise ValueError(f"PR #{pr_number} is not retryable from status {status}.")

    connection.execute(
        """
        UPDATE analysis_queue
        SET status = ?,
            attempts = ?,
            locked_at = ?,
            locked_by = ?,
            last_error = NULL,
            updated_at = ?
        WHERE pr_id = ?
        """,
        (QUEUE_STATUS_RUNNING, attempts, now, locked_by, now, pr_id),
    )
    cursor = connection.execute(
        """
        INSERT INTO analysis_runs(
            pr_id,
            run_id,
            started_at,
            status,
            task_dir
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (pr_id, run_id, now, "RUNNING", str(task_dir)),
    )
    return AnalysisStart(
        pr_id=pr_id,
        analysis_run_id=int(cursor.lastrowid),
        run_id=run_id,
        attempts=attempts,
    )


def finish_analysis_run(
    connection: sqlite3.Connection,
    *,
    pr_id: int,
    analysis_run_id: int,
    codex_exit_code: int | None,
    timed_out: bool,
    result_json_path: Path,
    notes_path: Path | None,
    stdout_log_path: Path,
    stderr_log_path: Path,
    attempts: int,
    max_attempts: int,
    last_error: str | None = None,
) -> None:
    now = _utc_now()
    if timed_out:
        run_status = "TIMEOUT"
    elif codex_exit_code == 0:
        run_status = "CODEX_EXITED"
    else:
        run_status = "FAILED_INFRA"

    connection.execute(
        """
        UPDATE analysis_runs
        SET finished_at = ?,
            codex_exit_code = ?,
            status = ?,
            result_json_path = ?,
            notes_path = ?,
            stdout_log_path = ?,
            stderr_log_path = ?
        WHERE id = ?
        """,
        (
            now,
            codex_exit_code,
            run_status,
            str(result_json_path),
            str(notes_path) if notes_path is not None else None,
            str(stdout_log_path),
            str(stderr_log_path),
            analysis_run_id,
        ),
    )

    if codex_exit_code == 0 and not timed_out:
        return

    queue_status = (
        QUEUE_STATUS_NEEDS_RETRY if attempts < max_attempts else QUEUE_STATUS_FAILED_INFRA
    )
    if last_error is None:
        last_error = (
            "Codex timed out." if timed_out else f"Codex exited with {codex_exit_code}."
        )
    connection.execute(
        """
        UPDATE analysis_queue
        SET status = ?,
            locked_at = NULL,
            locked_by = NULL,
            last_error = ?,
            updated_at = ?
        WHERE pr_id = ?
        """,
        (queue_status, last_error, now, pr_id),
    )


def finish_result_validation(
    connection: sqlite3.Connection,
    *,
    pr_id: int,
    analysis_run_id: int,
    valid: bool,
    attempts: int,
    max_attempts: int,
    last_error: str | None = None,
) -> None:
    now = _utc_now()
    if valid:
        run_status = "VALIDATED"
        queue_status = QUEUE_STATUS_VALIDATED
        stored_error = None
    else:
        run_status = "INVALID_RESULT"
        queue_status = (
            QUEUE_STATUS_NEEDS_RETRY
            if attempts < max_attempts
            else QUEUE_STATUS_FAILED_INFRA
        )
        stored_error = last_error or "Codex result failed validation."

    connection.execute(
        """
        UPDATE analysis_runs
        SET status = ?
        WHERE id = ?
        """,
        (run_status, analysis_run_id),
    )
    connection.execute(
        """
        UPDATE analysis_queue
        SET status = ?,
            locked_at = NULL,
            locked_by = NULL,
            last_error = ?,
            updated_at = ?
        WHERE pr_id = ?
        """,
        (queue_status, stored_error, now, pr_id),
    )


def store_validated_decision(
    connection: sqlite3.Connection,
    *,
    pr_id: int,
    analysis_run_id: int,
    result: CodexResult,
) -> int:
    now = _utc_now()
    queue_status = queue_status_for_decision(result.decision)

    cursor = connection.execute(
        """
        INSERT INTO decisions(
            pr_id,
            analysis_run_id,
            decision,
            confidence,
            bugfix_classification,
            applies_to_oss_015,
            reason,
            human_action,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            analysis_run_id,
            result.decision.value,
            result.confidence.value,
            result.bugfix_classification,
            _optional_bool_to_int(result.applicability.applies_to_oss_015),
            result.applicability.reason,
            result.human_action,
            now,
        ),
    )
    decision_id = int(cursor.lastrowid)

    connection.executemany(
        """
        INSERT INTO evidence(
            decision_id,
            evidence_type,
            description,
            file_path,
            command,
            exit_code,
            log_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                decision_id,
                evidence.type.value,
                evidence.description,
                evidence.path,
                evidence.command,
                evidence.exit_code,
                evidence.log_path,
            )
            for evidence in result.evidence
        ],
    )

    test_run_rows = _test_run_rows_for_result(
        analysis_run_id=analysis_run_id,
        result=result,
    )
    if test_run_rows:
        connection.executemany(
            """
            INSERT INTO test_runs(
                analysis_run_id,
                phase,
                command,
                exit_code,
                result,
                log_path,
                started_at,
                finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            test_run_rows,
        )

    connection.execute(
        """
        UPDATE analysis_queue
        SET status = ?,
            locked_at = NULL,
            locked_by = NULL,
            last_error = NULL,
            updated_at = ?
        WHERE pr_id = ?
        """,
        (queue_status, now, pr_id),
    )
    return decision_id


def queue_status_for_decision(decision: Decision) -> str:
    if decision is Decision.FAILED_INFRA:
        return QUEUE_STATUS_FAILED_INFRA
    if decision in {
        Decision.MASTER_NOT_APPLICABLE,
        Decision.DISCARDED_NON_BUGFIX,
        Decision.DISCARDED_DOCS_ONLY,
        Decision.DISCARDED_CI_ONLY,
        Decision.DISCARDED_RELEASE_ONLY,
    }:
        return QUEUE_STATUS_DONE
    return QUEUE_STATUS_REPORTABLE


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


def get_pull_request_inspection(
    connection: sqlite3.Connection,
    *,
    pr_number: int,
) -> InspectedPullRequest | None:
    pr_row = connection.execute(
        """
        SELECT
            prs.id,
            prs.github_pr_number,
            prs.github_pr_url,
            prs.title,
            prs.body,
            prs.source_branch,
            prs.target_branch,
            prs.merged_commit_sha,
            prs.created_at,
            prs.updated_at,
            prs.closed_at,
            prs.merged_at,
            prs.author,
            analysis_queue.status,
            analysis_queue.priority,
            analysis_queue.attempts,
            analysis_queue.next_retry_at,
            analysis_queue.locked_at,
            analysis_queue.locked_by,
            analysis_queue.last_error
        FROM prs
        LEFT JOIN analysis_queue ON analysis_queue.pr_id = prs.id
        WHERE prs.github_pr_number = ?
        ORDER BY prs.target_branch ASC
        LIMIT 1
        """,
        (pr_number,),
    ).fetchone()

    if pr_row is None:
        return None

    pr_id = int(pr_row[0])
    queue = None
    if pr_row[13] is not None:
        queue = InspectedQueueState(
            status=str(pr_row[13]),
            priority=int(pr_row[14]),
            attempts=int(pr_row[15]),
            next_retry_at=pr_row[16],
            locked_at=pr_row[17],
            locked_by=pr_row[18],
            last_error=pr_row[19],
        )

    files = _get_inspected_files(connection, pr_id)
    latest_analysis_run = _get_latest_inspected_analysis_run(connection, pr_id)
    latest_decision = _get_latest_inspected_decision(connection, pr_id)
    evidence: list[InspectedEvidence] = []
    test_runs: list[InspectedTestRun] = []

    if latest_decision is not None:
        evidence = _get_inspected_evidence(
            connection,
            pr_id=pr_id,
            analysis_run_id=latest_decision.analysis_run_id,
        )

    if latest_analysis_run is not None:
        test_runs = _get_inspected_test_runs(
            connection,
            analysis_run_id=latest_analysis_run.id,
        )

    return InspectedPullRequest(
        github_pr_number=int(pr_row[1]),
        github_pr_url=str(pr_row[2]),
        title=str(pr_row[3]),
        body=pr_row[4],
        source_branch=pr_row[5],
        target_branch=str(pr_row[6]),
        merged_commit_sha=pr_row[7],
        created_at=pr_row[8],
        updated_at=pr_row[9],
        closed_at=pr_row[10],
        merged_at=str(pr_row[11]),
        author=pr_row[12],
        queue=queue,
        files=files,
        latest_analysis_run=latest_analysis_run,
        latest_decision=latest_decision.decision if latest_decision else None,
        evidence=evidence,
        test_runs=test_runs,
        human_review=_get_latest_human_review(connection, pr_id),
    )


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


def _optional_bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _test_run_rows_for_result(
    *,
    analysis_run_id: int,
    result: CodexResult,
) -> list[tuple[int, str, str | None, int | None, str, str | None, None, None]]:
    rows: list[tuple[int, str, str | None, int | None, str, str | None, None, None]] = []

    if _should_store_test_run(
        attempted=result.test_before_fix.attempted,
        command=result.test_before_fix.command,
        exit_code=result.test_before_fix.exit_code,
        result_value=result.test_before_fix.result.value
        if result.test_before_fix.result is not None
        else None,
        log_path=result.test_before_fix.log_path,
    ):
        rows.append(
            (
                analysis_run_id,
                "test_before_fix",
                result.test_before_fix.command,
                result.test_before_fix.exit_code,
                result.test_before_fix.result.value
                if result.test_before_fix.result is not None
                else "not_run",
                result.test_before_fix.log_path,
                None,
                None,
            )
        )

    if _should_store_test_run(
        attempted=result.fix_verification.attempted,
        command=result.fix_verification.command,
        exit_code=result.fix_verification.exit_code,
        result_value=result.fix_verification.result.value
        if result.fix_verification.result is not None
        else None,
        log_path=result.fix_verification.log_path,
    ):
        rows.append(
            (
                analysis_run_id,
                "fix_verification",
                result.fix_verification.command,
                result.fix_verification.exit_code,
                result.fix_verification.result.value
                if result.fix_verification.result is not None
                else "not_run",
                result.fix_verification.log_path,
                None,
                None,
            )
        )

    return rows


def _should_store_test_run(
    *,
    attempted: bool,
    command: str | None,
    exit_code: int | None,
    result_value: str | None,
    log_path: str | None,
) -> bool:
    meaningful_result = result_value is not None and result_value != "not_run"
    return attempted or any(
        value is not None for value in (command, exit_code, log_path)
    ) or meaningful_result


@dataclass(frozen=True)
class _LatestDecisionWithRunId:
    analysis_run_id: int
    decision: InspectedDecision


def _get_inspected_files(
    connection: sqlite3.Connection,
    pr_id: int,
) -> list[InspectedPullRequestFile]:
    rows = connection.execute(
        """
        SELECT
            filename,
            status,
            additions,
            deletions,
            is_test_file,
            is_docs_file,
            is_ci_file
        FROM pr_files
        WHERE pr_id = ?
        ORDER BY filename ASC
        """,
        (pr_id,),
    ).fetchall()

    return [
        InspectedPullRequestFile(
            filename=str(row[0]),
            status=row[1],
            additions=row[2],
            deletions=row[3],
            is_test_file=bool(row[4]),
            is_docs_file=bool(row[5]),
            is_ci_file=bool(row[6]),
        )
        for row in rows
    ]


def _get_latest_inspected_decision(
    connection: sqlite3.Connection,
    pr_id: int,
) -> _LatestDecisionWithRunId | None:
    row = connection.execute(
        """
        SELECT
            decisions.analysis_run_id,
            decisions.decision,
            decisions.confidence,
            decisions.bugfix_classification,
            decisions.applies_to_oss_015,
            decisions.reason,
            decisions.human_action,
            decisions.created_at,
            analysis_runs.run_id,
            analysis_runs.started_at,
            analysis_runs.finished_at,
            analysis_runs.codex_exit_code,
            analysis_runs.status,
            analysis_runs.task_dir,
            analysis_runs.result_json_path,
            analysis_runs.notes_path,
            analysis_runs.stdout_log_path,
            analysis_runs.stderr_log_path
        FROM decisions
        JOIN analysis_runs ON analysis_runs.id = decisions.analysis_run_id
        WHERE decisions.pr_id = ?
        ORDER BY decisions.created_at DESC, decisions.id DESC
        LIMIT 1
        """,
        (pr_id,),
    ).fetchone()

    if row is None:
        return None

    applies_to_oss_015 = None
    if row[4] is not None:
        applies_to_oss_015 = bool(row[4])

    return _LatestDecisionWithRunId(
        analysis_run_id=int(row[0]),
        decision=InspectedDecision(
            decision=str(row[1]),
            confidence=str(row[2]),
            bugfix_classification=row[3],
            applies_to_oss_015=applies_to_oss_015,
            reason=str(row[5]),
            human_action=row[6],
            created_at=str(row[7]),
            analysis_run=InspectedAnalysisRun(
                id=int(row[0]),
                run_id=str(row[8]),
                started_at=str(row[9]),
                finished_at=row[10],
                codex_exit_code=row[11],
                status=str(row[12]),
                task_dir=str(row[13]),
                result_json_path=row[14],
                notes_path=row[15],
                stdout_log_path=row[16],
                stderr_log_path=row[17],
            ),
        ),
    )


def _get_latest_inspected_analysis_run(
    connection: sqlite3.Connection,
    pr_id: int,
) -> InspectedAnalysisRun | None:
    row = connection.execute(
        """
        SELECT
            id,
            run_id,
            started_at,
            finished_at,
            codex_exit_code,
            status,
            task_dir,
            result_json_path,
            notes_path,
            stdout_log_path,
            stderr_log_path
        FROM analysis_runs
        WHERE pr_id = ?
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """,
        (pr_id,),
    ).fetchone()

    if row is None:
        return None

    return InspectedAnalysisRun(
        id=int(row[0]),
        run_id=str(row[1]),
        started_at=str(row[2]),
        finished_at=row[3],
        codex_exit_code=row[4],
        status=str(row[5]),
        task_dir=str(row[6]),
        result_json_path=row[7],
        notes_path=row[8],
        stdout_log_path=row[9],
        stderr_log_path=row[10],
    )


def _get_inspected_evidence(
    connection: sqlite3.Connection,
    *,
    pr_id: int,
    analysis_run_id: int,
) -> list[InspectedEvidence]:
    rows = connection.execute(
        """
        SELECT
            evidence.evidence_type,
            evidence.description,
            evidence.file_path,
            evidence.command,
            evidence.exit_code,
            evidence.log_path
        FROM evidence
        JOIN decisions ON decisions.id = evidence.decision_id
        WHERE decisions.pr_id = ? AND decisions.analysis_run_id = ?
        ORDER BY evidence.id ASC
        """,
        (pr_id, analysis_run_id),
    ).fetchall()

    return [
        InspectedEvidence(
            evidence_type=str(row[0]),
            description=str(row[1]),
            file_path=row[2],
            command=row[3],
            exit_code=row[4],
            log_path=row[5],
        )
        for row in rows
    ]


def _get_inspected_test_runs(
    connection: sqlite3.Connection,
    *,
    analysis_run_id: int,
) -> list[InspectedTestRun]:
    rows = connection.execute(
        """
        SELECT
            phase,
            command,
            exit_code,
            result,
            log_path,
            started_at,
            finished_at
        FROM test_runs
        WHERE analysis_run_id = ?
        ORDER BY id ASC
        """,
        (analysis_run_id,),
    ).fetchall()

    return [
        InspectedTestRun(
            phase=str(row[0]),
            command=row[1],
            exit_code=row[2],
            result=str(row[3]),
            log_path=row[4],
            started_at=row[5],
            finished_at=row[6],
        )
        for row in rows
    ]


def _get_latest_human_review(
    connection: sqlite3.Connection,
    pr_id: int,
) -> InspectedHumanReview | None:
    row = connection.execute(
        """
        SELECT status, reviewer, comment, updated_at
        FROM human_reviews
        WHERE pr_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (pr_id,),
    ).fetchone()

    if row is None:
        return None

    return InspectedHumanReview(
        status=str(row[0]),
        reviewer=row[1],
        comment=row[2],
        updated_at=str(row[3]),
    )
