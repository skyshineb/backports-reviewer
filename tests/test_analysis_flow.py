from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from backport_harness.analysis_runner import analyze_one_pr
from backport_harness.storage import connect, init_database
from tests.fakes import (
    codex_run_result,
    insert_saved_pr,
    make_config,
    make_task_bundle,
    queue_row,
    write_valid_codex_result,
)


def test_analysis_flow_locks_pr_before_task_build_and_stores_reportable_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    bundle = make_task_bundle(tmp_path)
    write_valid_codex_result(bundle.task_dir)

    with connect(config.storage.sqlite_path) as connection:
        pr_id = insert_saved_pr(connection)

    def fake_build_task_bundle(**kwargs):
        assert queue_row(config.storage.sqlite_path, pr_id)[0] == "CODEX_RUNNING"
        return bundle

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        fake_build_task_bundle,
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: codex_run_result(bundle.task_dir),
    )

    result = analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        final_queue_row = queue_row(config.storage.sqlite_path, pr_id)
        run_row = connection.execute(
            "SELECT status, codex_exit_code FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()
        decision_row = connection.execute(
            "SELECT decision, confidence FROM decisions WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()

    assert result.validation is not None
    assert result.validation.valid is True
    assert final_queue_row == ("REPORTABLE", 1, None, None, None)
    assert run_row == ("VALIDATED", 0)
    assert decision_row == ("MASTER_FIX_VERIFIED_ON_015", "very_high")


def test_analysis_flow_timeout_marks_pr_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    bundle = make_task_bundle(tmp_path)

    with connect(config.storage.sqlite_path) as connection:
        pr_id = insert_saved_pr(connection)

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        lambda **kwargs: bundle,
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: codex_run_result(bundle.task_dir, exit_code=None, timed_out=True),
    )

    result = analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        run_row = connection.execute(
            "SELECT status, codex_exit_code FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()

    assert result.validation is None
    assert queue_row(config.storage.sqlite_path, pr_id) == (
        "NEEDS_RETRY",
        1,
        None,
        None,
        "Codex timed out.",
    )
    assert run_row == ("TIMEOUT", None)


def test_analysis_flow_nonzero_exit_preserves_logs_and_marks_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    bundle = make_task_bundle(tmp_path)

    with connect(config.storage.sqlite_path) as connection:
        pr_id = insert_saved_pr(connection)

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        lambda **kwargs: bundle,
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: codex_run_result(
            bundle.task_dir,
            exit_code=2,
            stdout="partial stdout\n",
            stderr="codex failed\n",
        ),
    )

    result = analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        run_row = connection.execute(
            """
            SELECT status, codex_exit_code, stdout_log_path, stderr_log_path
            FROM analysis_runs
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()

    assert result.validation is None
    assert queue_row(config.storage.sqlite_path, pr_id) == (
        "NEEDS_RETRY",
        1,
        None,
        None,
        "Codex exited with 2.",
    )
    assert run_row[0:2] == ("FAILED_INFRA", 2)
    assert Path(run_row[2]).read_text(encoding="utf-8") == "partial stdout\n"
    assert Path(run_row[3]).read_text(encoding="utf-8") == "codex failed\n"


def test_analysis_flow_malformed_result_marks_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    init_database(config.storage.sqlite_path)
    bundle = make_task_bundle(tmp_path)
    (bundle.output_dir / "codex_result.json").write_text("{", encoding="utf-8")

    with connect(config.storage.sqlite_path) as connection:
        pr_id = insert_saved_pr(connection)

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        lambda **kwargs: bundle,
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: codex_run_result(bundle.task_dir),
    )

    with pytest.raises(RuntimeError, match="failed validation"):
        analyze_one_pr(config=config, pr_number=12345)

    with connect(config.storage.sqlite_path) as connection:
        run_status = connection.execute(
            "SELECT status FROM analysis_runs WHERE pr_id = ?",
            (pr_id,),
        ).fetchone()[0]

    final_queue_row = queue_row(config.storage.sqlite_path, pr_id)
    assert final_queue_row[0:4] == ("NEEDS_RETRY", 1, None, None)
    assert "Invalid Codex result JSON" in final_queue_row[4]
    assert run_status == "INVALID_RESULT"


def test_analysis_flow_invalid_result_at_max_attempts_marks_failed_infra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path)
    config = replace(config, codex=replace(config.codex, max_attempts_per_pr=1))
    init_database(config.storage.sqlite_path)
    bundle = make_task_bundle(tmp_path)
    write_valid_codex_result(bundle.task_dir)
    (bundle.output_dir / "logs" / "test-before-fix.log").unlink()

    with connect(config.storage.sqlite_path) as connection:
        pr_id = insert_saved_pr(connection)

    monkeypatch.setattr(
        "backport_harness.analysis_runner.build_task_bundle",
        lambda **kwargs: bundle,
    )
    monkeypatch.setattr(
        "backport_harness.analysis_runner.run_codex",
        lambda request: codex_run_result(bundle.task_dir),
    )

    with pytest.raises(RuntimeError, match="failed validation"):
        analyze_one_pr(config=config, pr_number=12345)

    final_queue_row = queue_row(config.storage.sqlite_path, pr_id)
    assert final_queue_row[0:4] == ("FAILED_INFRA", 1, None, None)
    assert "Referenced log file is missing" in final_queue_row[4]
