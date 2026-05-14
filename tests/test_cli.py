from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from backport_harness import __version__
from backport_harness.main import app
from backport_harness.storage import connect, init_database


runner = CliRunner()


def write_valid_config(config_path: Path, sqlite_path: Path | None = None) -> None:
    storage_path = sqlite_path or config_path.parent / "workspace" / "db.sqlite3"
    config_path.write_text(
        f"""
github:
  owner: apache
  repo: hudi
  branches:
    - master
    - "0.15"
  token_env: GITHUB_TOKEN

local_repo:
  upstream_url: https://github.com/apache/hudi.git
  repo_dir: ./workspace/upstream
  worktree_dir: ./workspace/worktrees

codex:
  command: codex
  mode: exec
  max_attempts_per_pr: 2
  result_file: output/codex_result.json

reports:
  output_dir: ./reports

storage:
  sqlite_path: {storage_path}
""".lstrip(),
        encoding="utf-8",
    )


def test_help_shows_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "db" in result.output
    assert "analyze" in result.output
    assert "inspect" in result.output
    assert "list-prs" in result.output
    assert "prepare" in result.output
    assert "scan" in result.output
    assert "version" in result.output


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_accepts_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(app, ["--config", str(config_path), "version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_verbose_logging_option_does_not_crash() -> None:
    result = runner.invoke(app, ["--verbose", "version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_db_init_creates_configured_database(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)

    first_result = runner.invoke(app, ["--config", str(config_path), "db", "init"])
    second_result = runner.invoke(app, ["--config", str(config_path), "db", "init"])

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert sqlite_path.is_file()


def test_scan_command_passes_filters_to_scanner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    calls = []

    def fake_scan_pull_requests(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(branches=[object()], prs_seen=2, prs_saved=2)

    monkeypatch.setattr(
        "backport_harness.main.scan_pull_requests",
        fake_scan_pull_requests,
    )

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "scan",
            "--from-date",
            "2024-01-01",
            "--to-date",
            "2024-12-31",
            "--branch",
            "master",
        ],
    )

    assert result.exit_code == 0
    assert "saw 2 PR(s), saved 2 PR(s)" in result.output
    assert calls[0]["from_date"] == "2024-01-01"
    assert calls[0]["to_date"] == "2024-12-31"
    assert calls[0]["branch"] == "master"


def test_scan_command_rejects_invalid_date(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "scan",
            "--from-date",
            "20240101",
        ],
    )

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output


def test_scan_command_reports_unconfigured_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    def fake_scan_pull_requests(**kwargs):
        raise ValueError("Branch 'unknown' is not configured.")

    monkeypatch.setattr(
        "backport_harness.main.scan_pull_requests",
        fake_scan_pull_requests,
    )

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "scan",
            "--from-date",
            "2024-01-01",
            "--branch",
            "unknown",
        ],
    )

    assert result.exit_code != 0
    assert "not configured" in result.output


def test_list_prs_reports_empty_database(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)

    result = runner.invoke(app, ["--config", str(config_path), "list-prs"])

    assert result.exit_code == 0
    assert "No saved PRs found." in result.output


def test_list_prs_displays_saved_prs(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path)

    result = runner.invoke(app, ["--config", str(config_path), "list-prs"])

    assert result.exit_code == 0
    assert "#12345" in result.output
    assert "master" in result.output
    assert "QUEUED_FOR_ANALYSIS" in result.output
    assert "Fix compaction bug" in result.output


def test_list_prs_rejects_invalid_date(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "list-prs",
            "--from-date",
            "20240101",
        ],
    )

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output


def test_list_prs_rejects_invalid_order_by(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "list-prs",
            "--order-by",
            "title",
        ],
    )

    assert result.exit_code != 0
    assert "order-by" in result.output


def test_list_prs_rejects_invalid_limit(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "list-prs",
            "--limit",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_inspect_reports_missing_pr(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "inspect",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code != 0
    assert "No saved PR found for #12345" in result.output


def test_inspect_rejects_invalid_pr_number(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "inspect",
            "--pr",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_inspect_displays_pre_analysis_pr(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, with_file=True)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "inspect",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert "#12345" in result.output
    assert "Fix compaction bug" in result.output
    assert "QUEUED_FOR_ANALYSIS" in result.output
    assert "src/test/TestCompaction.java" in result.output
    assert "No decision recorded yet." in result.output


def test_inspect_displays_post_analysis_details(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, with_file=True, with_analysis=True)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "inspect",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert "MASTER_NOT_APPLICABLE" in result.output
    assert "Affected file is absent on 0.15" in result.output
    assert "workspace/tasks/pr-12345/output/stdout.log" in result.output
    assert "mvn test" in result.output
    assert "accepted_for_backport" in result.output


def test_inspect_displays_failed_analysis_run_without_decision(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, with_failed_analysis=True)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "inspect",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert "No decision recorded yet." in result.output
    assert "failed-run" in result.output
    assert "workspace/tasks/pr-12345/output/failed-stdout.log" in result.output
    assert "mvn test" in result.output


def test_analyze_dry_run_reports_empty_database(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "No analysis candidates found." in result.output


def test_analyze_dry_run_displays_candidates(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--dry-run",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "#12345" in result.output
    assert "QUEUED_FOR_ANALYSIS" in result.output
    assert "Fix compaction bug" in result.output


def test_analyze_without_dry_run_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
        ],
    )

    assert result.exit_code != 0
    assert "not implemented yet" in result.output


def test_analyze_rejects_invalid_limit(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--dry-run",
            "--limit",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_prepare_command_passes_pr_to_worktree_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    worktree_path = tmp_path / "workspace" / "worktrees" / "pr-12345-015"
    write_valid_config(config_path)
    calls = []

    def fake_prepare_oss_015_worktree(config, *, pr_number):
        calls.append((config, pr_number))
        return worktree_path

    monkeypatch.setattr(
        "backport_harness.main.prepare_oss_015_worktree",
        fake_prepare_oss_015_worktree,
    )

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][1] == 12345
    assert str(worktree_path) in result.output


def test_prepare_command_rejects_invalid_pr(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare",
            "--pr",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_prepare_command_reports_manager_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    def fake_prepare_oss_015_worktree(config, *, pr_number):
        raise RuntimeError("git failed")

    monkeypatch.setattr(
        "backport_harness.main.prepare_oss_015_worktree",
        fake_prepare_oss_015_worktree,
    )

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code != 0
    assert "git failed" in result.output


def _insert_saved_pr(
    sqlite_path: Path,
    *,
    with_file: bool = False,
    with_analysis: bool = False,
    with_failed_analysis: bool = False,
) -> None:
    with connect(sqlite_path) as connection:
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
                12345,
                "https://github.com/apache/hudi/pull/12345",
                "Fix compaction bug",
                "master",
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
                "QUEUED_FOR_ANALYSIS",
                100,
                0,
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
            ),
        )
        if with_file:
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
                    "src/test/TestCompaction.java",
                    "modified",
                    10,
                    2,
                    1,
                    0,
                    0,
                ),
            )
        if with_analysis:
            analysis_run_id = _insert_analysis_details(connection, pr_id=pr_id)
            decision_id = _insert_decision_details(
                connection,
                pr_id=pr_id,
                analysis_run_id=analysis_run_id,
            )
            _insert_evidence_details(connection, decision_id=decision_id)
            _insert_test_details(connection, analysis_run_id=analysis_run_id)
            _insert_review_details(connection, pr_id=pr_id)
        if with_failed_analysis:
            analysis_run_id = _insert_analysis_details(
                connection,
                pr_id=pr_id,
                run_id="failed-run",
                stdout_log_path="workspace/tasks/pr-12345/output/failed-stdout.log",
            )
            _insert_test_details(connection, analysis_run_id=analysis_run_id)


def _insert_analysis_details(
    connection,
    *,
    pr_id: int,
    run_id: str = "run-1",
    stdout_log_path: str = "workspace/tasks/pr-12345/output/stdout.log",
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
            "workspace/tasks/pr-12345",
            "workspace/tasks/pr-12345/output/codex_result.json",
            "workspace/tasks/pr-12345/output/notes.md",
            stdout_log_path,
            "workspace/tasks/pr-12345/output/stderr.log",
        ),
    )
    return int(cursor.lastrowid)


def _insert_decision_details(
    connection,
    *,
    pr_id: int,
    analysis_run_id: int,
) -> int:
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
            "MASTER_NOT_APPLICABLE",
            "high",
            "bugfix",
            0,
            "Affected file is absent on 0.15",
            "No action required",
            "2024-01-01T00:10:00Z",
        ),
    )
    return int(cursor.lastrowid)


def _insert_evidence_details(connection, *, decision_id: int) -> None:
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
            "workspace/tasks/pr-12345/output/evidence.log",
        ),
    )


def _insert_test_details(connection, *, analysis_run_id: int) -> None:
    connection.execute(
        """
        INSERT INTO test_runs(
            analysis_run_id,
            phase,
            command,
            exit_code,
            result,
            log_path
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            analysis_run_id,
            "after_fix",
            "mvn test",
            0,
            "passed",
            "workspace/tasks/pr-12345/output/test.log",
        ),
    )


def _insert_review_details(connection, *, pr_id: int) -> None:
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
            "accepted_for_backport",
            "reviewer",
            "Relevant",
            "2024-01-01T00:20:00Z",
        ),
    )
