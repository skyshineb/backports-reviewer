from pathlib import Path

import pytest

from backport_harness.codex_result import Decision, parse_codex_result_json
from backport_harness.storage import (
    connect,
    create_analysis_queue_row_if_missing,
    finish_analysis_run,
    finish_result_validation,
    get_pull_request_inspection,
    init_database,
    list_saved_pull_requests,
    queue_status_for_decision,
    select_analysis_candidates,
    start_analysis_run,
    store_validated_decision,
)


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


def test_list_saved_pull_requests_returns_empty_list(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        rows = list_saved_pull_requests(connection)

    assert rows == []


def test_list_saved_pull_requests_filters_and_limits(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=1,
            title="Master fix",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=100,
        )
        _insert_saved_pr(
            connection,
            number=2,
            title="Release fix",
            branch="0.15",
            merged_at="2024-01-03T00:00:00Z",
            status="DONE",
            priority=10,
        )
        _insert_saved_pr(
            connection,
            number=3,
            title="Later fix",
            branch="master",
            merged_at="2024-01-05T00:00:00Z",
            status="DONE",
            priority=50,
        )

        branch_rows = list_saved_pull_requests(connection, branch="master")
        status_rows = list_saved_pull_requests(connection, status="DONE")
        date_rows = list_saved_pull_requests(
            connection,
            from_date="2024-01-03",
            to_date="2024-01-04",
        )
        limited_rows = list_saved_pull_requests(connection, limit=1)

    assert [row.github_pr_number for row in branch_rows] == [1, 3]
    assert [row.github_pr_number for row in status_rows] == [2, 3]
    assert [row.github_pr_number for row in date_rows] == [2]
    assert [row.github_pr_number for row in limited_rows] == [1]


def test_list_saved_pull_requests_supports_ordering(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=1,
            title="B branch",
            branch="master",
            merged_at="2024-01-03T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=100,
        )
        _insert_saved_pr(
            connection,
            number=2,
            title="A branch",
            branch="0.15",
            merged_at="2024-01-02T00:00:00Z",
            status="DONE",
            priority=10,
        )
        _insert_saved_pr(
            connection,
            number=3,
            title="C branch",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="FAILED_INFRA",
            priority=50,
        )

        by_merged_at = list_saved_pull_requests(connection, order_by="merged-at")
        by_branch = list_saved_pull_requests(connection, order_by="branch")
        by_priority = list_saved_pull_requests(connection, order_by="priority")
        by_status = list_saved_pull_requests(connection, order_by="status")

    assert [row.github_pr_number for row in by_merged_at] == [3, 2, 1]
    assert [row.github_pr_number for row in by_branch] == [2, 3, 1]
    assert [row.github_pr_number for row in by_priority] == [2, 3, 1]
    assert [row.github_pr_number for row in by_status] == [2, 3, 1]


def test_list_saved_pull_requests_returns_latest_decision(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=1,
            title="Decision fix",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="DONE",
            priority=100,
        )
        first_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-1")
        second_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-2")
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=first_run_id,
            decision="INCONCLUSIVE",
            created_at="2024-01-02T01:00:00Z",
        )
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=second_run_id,
            decision="MASTER_NOT_APPLICABLE",
            created_at="2024-01-02T02:00:00Z",
        )

        rows = list_saved_pull_requests(connection)

    assert rows[0].latest_decision == "MASTER_NOT_APPLICABLE"


def test_get_pull_request_inspection_returns_none_for_missing_pr(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        inspection = get_pull_request_inspection(connection, pr_number=12345)

    assert inspection is None


def test_get_pull_request_inspection_returns_pre_analysis_pr(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Inspect me",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=100,
        )
        _insert_pr_file(
            connection,
            pr_id=pr_id,
            filename="src/test/TestHoodie.java",
            is_test_file=True,
        )

        inspection = get_pull_request_inspection(connection, pr_number=12345)

    assert inspection is not None
    assert inspection.github_pr_number == 12345
    assert inspection.title == "Inspect me"
    assert inspection.queue is not None
    assert inspection.queue.status == "QUEUED_FOR_ANALYSIS"
    assert inspection.files[0].filename == "src/test/TestHoodie.java"
    assert inspection.files[0].is_test_file is True
    assert inspection.latest_analysis_run is None
    assert inspection.latest_decision is None
    assert inspection.evidence == []
    assert inspection.test_runs == []
    assert inspection.human_review is None


def test_get_pull_request_inspection_returns_post_analysis_details(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Analyzed PR",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="DONE",
            priority=50,
        )
        _insert_pr_file(
            connection,
            pr_id=pr_id,
            filename="src/main/Hoodie.java",
            is_test_file=False,
        )
        first_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-1")
        second_run_id = _insert_analysis_run(
            connection,
            pr_id=pr_id,
            run_id="run-2",
            stdout_log_path="workspace/tasks/pr-12345/output/stdout.log",
        )
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=first_run_id,
            decision="INCONCLUSIVE",
            created_at="2024-01-02T01:00:00Z",
        )
        latest_decision_id = _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=second_run_id,
            decision="MASTER_NOT_APPLICABLE",
            created_at="2024-01-02T02:00:00Z",
        )
        _insert_evidence(connection, decision_id=latest_decision_id)
        _insert_test_run(connection, analysis_run_id=second_run_id)
        _insert_human_review(connection, pr_id=pr_id, status="accepted_for_backport")

        inspection = get_pull_request_inspection(connection, pr_number=12345)

    assert inspection is not None
    assert inspection.latest_decision is not None
    assert inspection.latest_decision.decision == "MASTER_NOT_APPLICABLE"
    assert inspection.latest_analysis_run is not None
    assert inspection.latest_analysis_run.run_id == "run-2"
    assert inspection.latest_decision.analysis_run.run_id == "run-2"
    assert (
        inspection.latest_decision.analysis_run.stdout_log_path
        == "workspace/tasks/pr-12345/output/stdout.log"
    )
    assert len(inspection.evidence) == 1
    assert inspection.evidence[0].evidence_type == "file"
    assert len(inspection.test_runs) == 1
    assert inspection.test_runs[0].result == "passed"
    assert inspection.human_review is not None
    assert inspection.human_review.status == "accepted_for_backport"


def test_get_pull_request_inspection_returns_failed_run_without_decision(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Failed run PR",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="FAILED_INFRA",
            priority=50,
        )
        failed_run_id = _insert_analysis_run(
            connection,
            pr_id=pr_id,
            run_id="failed-run",
            stdout_log_path="workspace/tasks/pr-12345/output/failed-stdout.log",
        )
        _insert_test_run(connection, analysis_run_id=failed_run_id)

        inspection = get_pull_request_inspection(connection, pr_number=12345)

    assert inspection is not None
    assert inspection.latest_decision is None
    assert inspection.latest_analysis_run is not None
    assert inspection.latest_analysis_run.run_id == "failed-run"
    assert (
        inspection.latest_analysis_run.stdout_log_path
        == "workspace/tasks/pr-12345/output/failed-stdout.log"
    )
    assert len(inspection.test_runs) == 1
    assert inspection.test_runs[0].result == "passed"


def test_create_analysis_queue_row_assigns_computed_priority(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        direct_pr_id = _insert_pr_without_queue(
            connection,
            number=1,
            title="Add release fix",
            branch="0.15",
            merged_at="2024-01-01T00:00:00Z",
        )
        bugfix_pr_id = _insert_pr_without_queue(
            connection,
            number=2,
            title="Fix NPE in compaction",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
        )
        create_analysis_queue_row_if_missing(
            connection,
            direct_pr_id,
            target_branch="0.15",
            title="Add release fix",
        )
        create_analysis_queue_row_if_missing(
            connection,
            bugfix_pr_id,
            target_branch="master",
            title="Fix NPE in compaction",
        )

        rows = connection.execute(
            """
            SELECT prs.github_pr_number, analysis_queue.priority
            FROM analysis_queue
            JOIN prs ON prs.id = analysis_queue.pr_id
            ORDER BY prs.github_pr_number
            """
        ).fetchall()

    assert rows == [(1, 10), (2, 20)]


def test_create_analysis_queue_row_does_not_overwrite_existing_queue_state(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=1,
            title="Existing state",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="DONE",
            priority=7,
        )
        create_analysis_queue_row_if_missing(
            connection,
            pr_id,
            target_branch="0.15",
            title="Fix important bug",
        )

        row = connection.execute(
            """
            SELECT status, priority
            FROM analysis_queue
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()

    assert row == ("DONE", 7)


def test_select_analysis_candidates_orders_limits_and_skips_non_retryable(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=1,
            title="Done",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="DONE",
            priority=1,
        )
        _insert_saved_pr(
            connection,
            number=2,
            title="Queued low",
            branch="master",
            merged_at="2024-01-02T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=100,
        )
        _insert_saved_pr(
            connection,
            number=3,
            title="Retry high",
            branch="master",
            merged_at="2024-01-03T00:00:00Z",
            status="NEEDS_RETRY",
            priority=10,
        )
        _insert_saved_pr(
            connection,
            number=4,
            title="Queued same priority older",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=50,
        )
        _insert_saved_pr(
            connection,
            number=5,
            title="Running",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="CODEX_RUNNING",
            priority=1,
        )
        _insert_saved_pr(
            connection,
            number=6,
            title="Paused",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="PAUSED",
            priority=1,
        )
        _insert_saved_pr(
            connection,
            number=7,
            title="Failed infra",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="FAILED_INFRA",
            priority=1,
        )
        _insert_saved_pr(
            connection,
            number=8,
            title="Reportable",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="REPORTABLE",
            priority=1,
        )

        candidates = select_analysis_candidates(connection, limit=2)

    assert [candidate.github_pr_number for candidate in candidates] == [3, 4]
    assert candidates[0].queue_status == "NEEDS_RETRY"


def test_start_analysis_run_locks_queue_and_creates_run(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        queue_row = connection.execute(
            "SELECT status, attempts, locked_by FROM analysis_queue WHERE pr_id = ?",
            (started.pr_id,),
        ).fetchone()
        run_row = connection.execute(
            "SELECT run_id, status, task_dir FROM analysis_runs WHERE id = ?",
            (started.analysis_run_id,),
        ).fetchone()

    assert queue_row == ("CODEX_RUNNING", 1, "test-worker")
    assert run_row == ("run-1", "RUNNING", str(tmp_path / "tasks" / "pr-12345"))


def test_start_analysis_run_rejects_non_retryable_status(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Done",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="DONE",
            priority=20,
        )
        with pytest.raises(ValueError, match="not retryable"):
            start_analysis_run(
                connection,
                pr_number=12345,
                run_id="run-1",
                task_dir=tmp_path / "tasks" / "pr-12345",
                locked_by="test-worker",
            )


def test_start_analysis_run_rejects_running_without_creating_run(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Already running",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="CODEX_RUNNING",
            priority=20,
        )
        with pytest.raises(ValueError, match="not retryable"):
            start_analysis_run(
                connection,
                pr_number=12345,
                run_id="run-1",
                task_dir=tmp_path / "tasks" / "pr-12345",
                locked_by="test-worker",
            )

        queue_row = connection.execute(
            "SELECT status, attempts FROM analysis_queue WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()
        run_count = connection.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()[0]

    assert queue_row == ("CODEX_RUNNING", 0)
    assert run_count == 0


def test_finish_analysis_run_success_keeps_queue_running(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        finish_analysis_run(
            connection,
            pr_id=started.pr_id,
            analysis_run_id=started.analysis_run_id,
            codex_exit_code=0,
            timed_out=False,
            result_json_path=tmp_path / "tasks" / "pr-12345" / "output" / "codex_result.json",
            notes_path=tmp_path / "tasks" / "pr-12345" / "output" / "notes.md",
            stdout_log_path=tmp_path / "stdout.log",
            stderr_log_path=tmp_path / "stderr.log",
            attempts=started.attempts,
            max_attempts=2,
        )
        queue_status = connection.execute(
            "SELECT status FROM analysis_queue WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()[0]
        run_status = connection.execute(
            "SELECT status, codex_exit_code FROM analysis_runs WHERE id = ?",
            (started.analysis_run_id,),
        ).fetchone()

    assert queue_status == "CODEX_RUNNING"
    assert run_status == ("CODEX_EXITED", 0)


def test_finish_analysis_run_failure_updates_queue_status(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        finish_analysis_run(
            connection,
            pr_id=started.pr_id,
            analysis_run_id=started.analysis_run_id,
            codex_exit_code=1,
            timed_out=False,
            result_json_path=tmp_path / "result.json",
            notes_path=None,
            stdout_log_path=tmp_path / "stdout.log",
            stderr_log_path=tmp_path / "stderr.log",
            attempts=started.attempts,
            max_attempts=2,
        )
        queue_row = connection.execute(
            "SELECT status, locked_at, locked_by, last_error FROM analysis_queue WHERE pr_id = ?",
            (started.pr_id,),
        ).fetchone()

    assert queue_row == ("NEEDS_RETRY", None, None, "Codex exited with 1.")


def test_finish_result_validation_success_marks_validated(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        finish_result_validation(
            connection,
            pr_id=started.pr_id,
            analysis_run_id=started.analysis_run_id,
            valid=True,
            attempts=started.attempts,
            max_attempts=2,
        )
        queue_row = connection.execute(
            "SELECT status, locked_at, locked_by, last_error FROM analysis_queue WHERE pr_id = ?",
            (started.pr_id,),
        ).fetchone()
        run_status = connection.execute(
            "SELECT status FROM analysis_runs WHERE id = ?",
            (started.analysis_run_id,),
        ).fetchone()[0]

    assert queue_row == ("VALIDATED", None, None, None)
    assert run_status == "VALIDATED"


def test_finish_result_validation_failure_updates_queue_status(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        finish_result_validation(
            connection,
            pr_id=started.pr_id,
            analysis_run_id=started.analysis_run_id,
            valid=False,
            attempts=started.attempts,
            max_attempts=2,
            last_error="missing log",
        )
        queue_row = connection.execute(
            "SELECT status, locked_at, locked_by, last_error FROM analysis_queue WHERE pr_id = ?",
            (started.pr_id,),
        ).fetchone()
        run_status = connection.execute(
            "SELECT status FROM analysis_runs WHERE id = ?",
            (started.analysis_run_id,),
        ).fetchone()[0]

    assert queue_row == ("NEEDS_RETRY", None, None, "missing log")
    assert run_status == "INVALID_RESULT"


def test_finish_result_validation_failure_at_max_attempts_marks_failed_infra(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="QUEUED_FOR_ANALYSIS",
            priority=20,
        )
        started = start_analysis_run(
            connection,
            pr_number=12345,
            run_id="run-1",
            task_dir=tmp_path / "tasks" / "pr-12345",
            locked_by="test-worker",
        )
        finish_result_validation(
            connection,
            pr_id=started.pr_id,
            analysis_run_id=started.analysis_run_id,
            valid=False,
            attempts=started.attempts,
            max_attempts=1,
            last_error="malformed result",
        )
        queue_status = connection.execute(
            "SELECT status FROM analysis_queue WHERE pr_id = ?",
            (started.pr_id,),
        ).fetchone()[0]

    assert queue_status == "FAILED_INFRA"


def test_store_validated_decision_persists_decision_evidence_and_test_runs(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)
    result = _valid_codex_result()

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="VALIDATED",
            priority=20,
        )
        analysis_run_id = _insert_analysis_run(
            connection,
            pr_id=pr_id,
            run_id="run-1",
        )

        decision_id = store_validated_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=analysis_run_id,
            result=result,
        )

        decision_row = connection.execute(
            """
            SELECT decision, confidence, bugfix_classification, applies_to_oss_015,
                   reason, human_action
            FROM decisions
            WHERE id = ?
            """,
            (decision_id,),
        ).fetchone()
        evidence_rows = connection.execute(
            """
            SELECT evidence_type, description, file_path, command, exit_code, log_path
            FROM evidence
            WHERE decision_id = ?
            ORDER BY id
            """,
            (decision_id,),
        ).fetchall()
        test_run_rows = connection.execute(
            """
            SELECT phase, command, exit_code, result, log_path
            FROM test_runs
            WHERE analysis_run_id = ?
            ORDER BY id
            """,
            (analysis_run_id,),
        ).fetchall()
        queue_status = connection.execute(
            "SELECT status, locked_at, locked_by, last_error FROM analysis_queue WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()

    assert decision_row == (
        "MASTER_FIX_VERIFIED_ON_015",
        "very_high",
        "correctness_bugfix",
        1,
        "The affected class and method exist in OSS 0.15.",
        "Review adapted patch and backport if appropriate.",
    )
    assert evidence_rows == [
        (
            "code_presence",
            "Class Foo exists in OSS 0.15.",
            "hudi-client/src/main/java/example/Foo.java",
            None,
            None,
            None,
        ),
        (
            "test_failure",
            "Test fails with the expected error before the fix.",
            None,
            "mvn test",
            1,
            "output/logs/test-before-fix.log",
        ),
        (
            "test_pass",
            "Test passes after the adapted fix.",
            None,
            "mvn test",
            0,
            "output/logs/test-after-fix.log",
        ),
    ]
    assert test_run_rows == [
        (
            "test_before_fix",
            "mvn test",
            1,
            "failed_with_expected_error",
            "output/logs/test-before-fix.log",
        ),
        (
            "fix_verification",
            "mvn test",
            0,
            "passed_after_adapted_fix",
            "output/logs/test-after-fix.log",
        ),
    ]
    assert queue_status == ("REPORTABLE", None, None, None)


def test_store_validated_decision_preserves_previous_decisions(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=12345,
            title="Analyze me",
            branch="master",
            merged_at="2024-01-01T00:00:00Z",
            status="VALIDATED",
            priority=20,
        )
        first_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-1")
        second_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-2")
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=first_run_id,
            decision="INCONCLUSIVE",
            created_at="2024-01-01T00:05:00Z",
        )

        store_validated_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=second_run_id,
            result=_valid_codex_result(decision="MASTER_NOT_APPLICABLE"),
        )

        decision_rows = connection.execute(
            """
            SELECT analysis_run_id, decision
            FROM decisions
            WHERE pr_id = ?
            ORDER BY id
            """,
            (pr_id,),
        ).fetchall()
        listed = list_saved_pull_requests(connection)
        inspected = get_pull_request_inspection(connection, pr_number=12345)

    assert decision_rows == [
        (first_run_id, "INCONCLUSIVE"),
        (second_run_id, "MASTER_NOT_APPLICABLE"),
    ]
    assert listed[0].latest_decision == "MASTER_NOT_APPLICABLE"
    assert inspected is not None
    assert inspected.latest_decision is not None
    assert inspected.latest_decision.decision == "MASTER_NOT_APPLICABLE"


@pytest.mark.parametrize(
    ("decision", "queue_status"),
    [
        (Decision.DIRECT_015_BUGFIX, "REPORTABLE"),
        (Decision.MASTER_POSSIBLY_APPLICABLE, "REPORTABLE"),
        (Decision.MASTER_REPRODUCED_ON_015, "REPORTABLE"),
        (Decision.MASTER_FIX_VERIFIED_ON_015, "REPORTABLE"),
        (Decision.INCONCLUSIVE, "REPORTABLE"),
        (Decision.NEEDS_HUMAN_REVIEW, "REPORTABLE"),
        (Decision.MASTER_NOT_APPLICABLE, "DONE"),
        (Decision.DISCARDED_NON_BUGFIX, "DONE"),
        (Decision.DISCARDED_DOCS_ONLY, "DONE"),
        (Decision.DISCARDED_CI_ONLY, "DONE"),
        (Decision.DISCARDED_RELEASE_ONLY, "DONE"),
        (Decision.FAILED_INFRA, "FAILED_INFRA"),
    ],
)
def test_queue_status_for_decision(decision: Decision, queue_status: str) -> None:
    assert queue_status_for_decision(decision) == queue_status


def _valid_codex_result(*, decision: str = "MASTER_FIX_VERIFIED_ON_015"):
    return parse_codex_result_json(
        """
        {
          "schema_version": 1,
          "pr_number": 12345,
          "target_branch": "master",
          "decision": "%s",
          "confidence": "very_high",
          "bugfix_classification": "correctness_bugfix",
          "summary": "Fixes null handling in compaction scheduling.",
          "human_action": "Review adapted patch and backport if appropriate.",
          "applicability": {
            "applies_to_oss_015": true,
            "reason": "The affected class and method exist in OSS 0.15.",
            "affected_public_paths": [],
            "missing_public_paths": []
          },
          "test_transplant": {
            "attempted": true,
            "result": "applied_and_compiled",
            "notes": "Adapted imports."
          },
          "test_before_fix": {
            "attempted": true,
            "command": "mvn test",
            "exit_code": 1,
            "result": "failed_with_expected_error",
            "log_path": "output/logs/test-before-fix.log"
          },
          "fix_verification": {
            "attempted": true,
            "command": "mvn test",
            "exit_code": 0,
            "result": "passed_after_adapted_fix",
            "patch_path": "output/patches/adapted-fix.patch",
            "log_path": "output/logs/test-after-fix.log"
          },
          "evidence": [
            {
              "type": "code_presence",
              "description": "Class Foo exists in OSS 0.15.",
              "path": "hudi-client/src/main/java/example/Foo.java"
            },
            {
              "type": "test_failure",
              "description": "Test fails with the expected error before the fix.",
              "log_path": "output/logs/test-before-fix.log",
              "command": "mvn test",
              "exit_code": 1
            },
            {
              "type": "test_pass",
              "description": "Test passes after the adapted fix.",
              "log_path": "output/logs/test-after-fix.log",
              "patch_path": "output/patches/adapted-fix.patch",
              "command": "mvn test",
              "exit_code": 0
            }
          ]
        }
        """
        % decision
    )


def _insert_saved_pr(
    connection,
    *,
    number: int,
    title: str,
    branch: str,
    merged_at: str,
    status: str,
    priority: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            target_branch,
            merged_at,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            number,
            f"https://github.com/apache/hudi/pull/{number}",
            title,
            branch,
            merged_at,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    pr_id = int(cursor.lastrowid)
    connection.execute(
        """
        INSERT INTO analysis_queue(
            pr_id,
            status,
            priority,
            attempts,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            status,
            priority,
            0,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    return pr_id


def _insert_pr_without_queue(
    connection,
    *,
    number: int,
    title: str,
    branch: str,
    merged_at: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            target_branch,
            merged_at,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            number,
            f"https://github.com/apache/hudi/pull/{number}",
            title,
            branch,
            merged_at,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    return int(cursor.lastrowid)


def _insert_pr_file(
    connection,
    *,
    pr_id: int,
    filename: str,
    is_test_file: bool,
) -> None:
    connection.execute(
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
        (
            pr_id,
            filename,
            "modified",
            10,
            2,
            int(is_test_file),
            0,
            0,
        ),
    )


def _insert_analysis_run(
    connection,
    *,
    pr_id: int,
    run_id: str,
    stdout_log_path: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO analysis_runs(
            pr_id,
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            run_id,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:10:00Z",
            0,
            "DONE",
            "workspace/tasks/pr-1",
            "workspace/tasks/pr-1/output/codex_result.json",
            "workspace/tasks/pr-1/output/notes.md",
            stdout_log_path,
            "workspace/tasks/pr-1/output/stderr.log",
        ),
    )
    return int(cursor.lastrowid)


def _insert_decision(
    connection,
    *,
    pr_id: int,
    analysis_run_id: int,
    decision: str,
    created_at: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO decisions(
            pr_id,
            analysis_run_id,
            decision,
            confidence,
            reason,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pr_id, analysis_run_id, decision, "medium", "reason", created_at),
    )
    return int(cursor.lastrowid)


def _insert_evidence(connection, *, decision_id: int) -> None:
    connection.execute(
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
        (
            decision_id,
            "file",
            "Affected file is absent on 0.15",
            "src/main/Hoodie.java",
            "grep Hoodie",
            1,
            "workspace/tasks/pr-12345/output/logs/evidence.log",
        ),
    )


def _insert_test_run(connection, *, analysis_run_id: int) -> None:
    connection.execute(
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
        (
            analysis_run_id,
            "after_fix",
            "mvn test",
            0,
            "passed",
            "workspace/tasks/pr-12345/output/logs/test.log",
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:02:00Z",
        ),
    )


def _insert_human_review(connection, *, pr_id: int, status: str) -> None:
    connection.execute(
        """
        INSERT INTO human_reviews(
            pr_id,
            status,
            reviewer,
            comment,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            status,
            "reviewer",
            "Looks relevant",
            "2024-01-01T00:00:00Z",
        ),
    )
