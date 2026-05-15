from __future__ import annotations

from pathlib import Path

import pytest

from backport_harness.analysis_runner import analyze_one_pr
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
