from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backport_harness.analysis_runner import analyze_one_pr
from backport_harness.codex_runner import CodexRunResult
from backport_harness.storage import connect, init_database
from backport_harness.task_builder import TaskBundle
from tests.test_repo_manager import make_config


def test_analyze_one_pr_rejects_running_pr_before_rebuilding_task_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    task_dir = tmp_path / "workspace" / "tasks" / "pr-12345"
    task_dir.mkdir(parents=True)
    sentinel = task_dir / "in-flight.log"
    sentinel.write_text("keep me\n", encoding="utf-8")

    with connect(config.storage.sqlite_path) as connection:
        _insert_saved_pr(connection, status="CODEX_RUNNING")

    def fail_if_called(**kwargs):
        raise AssertionError("task bundle should not be rebuilt")

    monkeypatch.setattr("backport_harness.analysis_runner.build_task_bundle", fail_if_called)

    with pytest.raises(ValueError, match="not retryable"):
        analyze_one_pr(config=config, pr_number=12345)

    assert sentinel.read_text(encoding="utf-8") == "keep me\n"


def test_analyze_one_pr_marks_run_failed_when_codex_spawn_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    task_dir = tmp_path / "workspace" / "tasks" / "pr-12345"
    output_dir = task_dir / "output"
    logs_dir = output_dir / "logs"
    patches_dir = output_dir / "patches"
    instructions_path = task_dir / "instructions.md"
    instructions_path.parent.mkdir(parents=True)
    instructions_path.write_text("analyze this\n", encoding="utf-8")
    logs_dir.mkdir(parents=True)
    patches_dir.mkdir(parents=True)

    with connect(config.storage.sqlite_path) as connection:
        pr_id = _insert_saved_pr(connection, status="QUEUED_FOR_ANALYSIS")

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        lambda **kwargs: TaskBundle(
            pr_number=12345,
            task_dir=task_dir,
            worktree_path=tmp_path / "workspace" / "worktrees" / "pr-12345-015",
            pr_json_path=task_dir / "pr.json",
            files_changed_json_path=task_dir / "files_changed.json",
            diff_path=task_dir / "pr.diff",
            instructions_path=instructions_path,
            output_dir=output_dir,
            logs_dir=logs_dir,
            patches_dir=patches_dir,
        ),
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: (_ for _ in ()).throw(FileNotFoundError("codex")),
    )

    with pytest.raises(RuntimeError, match="FileNotFoundError"):
        analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, attempts, locked_at, locked_by, last_error
            FROM analysis_queue
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()
        run_row = connection.execute(
            """
            SELECT status, codex_exit_code, stdout_log_path, stderr_log_path
            FROM analysis_runs
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()

    assert queue_row[:4] == ("NEEDS_RETRY", 1, None, None)
    assert "FileNotFoundError: codex" in queue_row[4]
    assert run_row[0] == "FAILED_INFRA"
    assert run_row[1] is None
    assert Path(run_row[2]).read_text(encoding="utf-8") == ""
    assert "FileNotFoundError: codex" in Path(run_row[3]).read_text(encoding="utf-8")


def test_analyze_one_pr_stores_successful_validated_codex_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    config = replace(config, codex=replace(config.codex, reasoning_effort="high"))
    init_database(config.storage.sqlite_path)
    task_dir, bundle = _make_bundle(tmp_path)
    _write_valid_codex_result(task_dir)
    codex_requests = []

    with connect(config.storage.sqlite_path) as connection:
        pr_id = _insert_saved_pr(connection, status="QUEUED_FOR_ANALYSIS")

    monkeypatch.setattr("backport_harness.analysis_runner.build_task_bundle", lambda **kwargs: bundle)

    def capture_codex_request(request):
        codex_requests.append(request)
        return _successful_codex_run(request)

    monkeypatch.setattr("backport_harness.analysis_runner.run_codex", capture_codex_request)

    result = analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, locked_at, locked_by, last_error
            FROM analysis_queue
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()
        run_row = connection.execute(
            "SELECT status, codex_exit_code FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()
        decision_row = connection.execute(
            """
            SELECT decision, confidence, reason
            FROM decisions
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()
        evidence_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM evidence
            JOIN decisions ON decisions.id = evidence.decision_id
            WHERE decisions.pr_id = ?
            """,
            (pr_id,),
        ).fetchone()[0]
        test_run_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM test_runs
            WHERE analysis_run_id = (
                SELECT id FROM analysis_runs WHERE pr_id = ?
            )
            """,
            (pr_id,),
        ).fetchone()[0]

    assert result.validation is not None
    assert result.validation.valid is True
    assert codex_requests[0].reasoning_effort == "high"
    assert queue_row == ("REPORTABLE", None, None, None)
    assert run_row == ("VALIDATED", 0)
    assert decision_row == (
        "MASTER_FIX_VERIFIED_ON_015",
        "very_high",
        "The affected class and method exist in OSS 0.15.",
    )
    assert evidence_count == 3
    assert test_run_count == 2


def test_analyze_one_pr_invalid_result_is_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    task_dir, bundle = _make_bundle(tmp_path)
    _write_valid_codex_result(task_dir)
    (task_dir / "output" / "logs" / "test-before-fix.log").unlink()

    with connect(config.storage.sqlite_path) as connection:
        pr_id = _insert_saved_pr(connection, status="QUEUED_FOR_ANALYSIS")

    monkeypatch.setattr("backport_harness.analysis_runner.build_task_bundle", lambda **kwargs: bundle)
    monkeypatch.setattr("backport_harness.analysis_runner.run_codex", _successful_codex_run)

    with pytest.raises(RuntimeError, match="failed validation"):
        analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, locked_at, locked_by, last_error
            FROM analysis_queue
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()
        run_status = connection.execute(
            "SELECT status FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()[0]

    assert queue_row[0:3] == ("NEEDS_RETRY", None, None)
    assert "Referenced log file is missing" in queue_row[3]
    assert run_status == "INVALID_RESULT"


def test_analyze_one_pr_invalid_result_at_max_attempts_marks_failed_infra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    config = replace(config, codex=replace(config.codex, max_attempts_per_pr=1))
    init_database(config.storage.sqlite_path)
    task_dir, bundle = _make_bundle(tmp_path)
    _write_valid_codex_result(task_dir)
    (task_dir / "output" / "logs" / "test-before-fix.log").unlink()

    with connect(config.storage.sqlite_path) as connection:
        pr_id = _insert_saved_pr(connection, status="QUEUED_FOR_ANALYSIS")

    monkeypatch.setattr("backport_harness.analysis_runner.build_task_bundle", lambda **kwargs: bundle)
    monkeypatch.setattr("backport_harness.analysis_runner.run_codex", _successful_codex_run)

    with pytest.raises(RuntimeError, match="failed validation"):
        analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        queue_status = connection.execute(
            "SELECT status FROM analysis_queue WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()[0]

    assert queue_status == "FAILED_INFRA"


def _insert_saved_pr(connection, *, status: str) -> int:
    cursor = connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            target_branch,
            merged_commit_sha,
            merged_at,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            12345,
            "https://github.com/apache/hudi/pull/12345",
            "Analyze me",
            "master",
            "abc123",
            "2024-01-01T00:00:00Z",
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
            20,
            0,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    return pr_id


def _make_bundle(tmp_path: Path) -> tuple[Path, TaskBundle]:
    task_dir = tmp_path / "workspace" / "tasks" / "pr-12345"
    output_dir = task_dir / "output"
    logs_dir = output_dir / "logs"
    patches_dir = output_dir / "patches"
    instructions_path = task_dir / "instructions.md"
    logs_dir.mkdir(parents=True)
    patches_dir.mkdir(parents=True)
    instructions_path.write_text("analyze this\n", encoding="utf-8")
    return task_dir, TaskBundle(
        pr_number=12345,
        task_dir=task_dir,
        worktree_path=tmp_path / "workspace" / "worktrees" / "pr-12345-015",
        pr_json_path=task_dir / "pr.json",
        files_changed_json_path=task_dir / "files_changed.json",
        diff_path=task_dir / "pr.diff",
        instructions_path=instructions_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        patches_dir=patches_dir,
    )


def _successful_codex_run(request) -> CodexRunResult:
    return CodexRunResult(
        session_id="00000000-0000-0000-0000-000000000000",
        exit_code=0,
        timed_out=False,
        stdout_log_path=request.cwd / "output" / "logs" / "codex-stdout.log",
        stderr_log_path=request.cwd / "output" / "logs" / "codex-stderr.log",
        last_message_path=None,
        started_at="2024-01-01T00:00:00Z",
        finished_at="2024-01-01T00:01:00Z",
    )


def _write_valid_codex_result(task_dir: Path) -> None:
    (task_dir / "output" / "logs" / "test-before-fix.log").write_text(
        "before\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "logs" / "test-after-fix.log").write_text(
        "after\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "patches" / "adapted-fix.patch").write_text(
        "patch\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "codex_result.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pr_number": 12345,
                "target_branch": "master",
                "decision": "MASTER_FIX_VERIFIED_ON_015",
                "confidence": "very_high",
                "summary": "Fixes null handling in compaction scheduling.",
                "human_action": "Review adapted patch and backport if appropriate.",
                "applicability": {
                    "applies_to_oss_015": True,
                    "reason": "The affected class and method exist in OSS 0.15.",
                    "affected_public_paths": [
                        "hudi-client/src/main/java/example/Foo.java",
                    ],
                    "missing_public_paths": [],
                },
                "test_transplant": {
                    "attempted": True,
                    "result": "applied_and_compiled",
                    "notes": "Adapted imports.",
                },
                "test_before_fix": {
                    "attempted": True,
                    "command": "mvn test",
                    "exit_code": 1,
                    "result": "failed_with_expected_error",
                    "log_path": "output/logs/test-before-fix.log",
                },
                "fix_verification": {
                    "attempted": True,
                    "command": "mvn test",
                    "exit_code": 0,
                    "result": "passed_after_adapted_fix",
                    "patch_path": "output/patches/adapted-fix.patch",
                    "log_path": "output/logs/test-after-fix.log",
                },
                "evidence": [
                    {
                        "type": "code_presence",
                        "description": "Class Foo exists in OSS 0.15.",
                    },
                    {
                        "type": "test_failure",
                        "description": "Test fails with the expected error before the fix.",
                        "log_path": "output/logs/test-before-fix.log",
                        "exit_code": 1,
                    },
                    {
                        "type": "test_pass",
                        "description": "Test passes after the adapted fix.",
                        "log_path": "output/logs/test-after-fix.log",
                        "patch_path": "output/patches/adapted-fix.patch",
                        "exit_code": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
