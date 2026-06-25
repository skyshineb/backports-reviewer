from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from backport_harness import __version__
from backport_harness.main import app
from backport_harness.storage import connect, init_database
from backport_harness.task_builder import TaskBundle


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
  branch_ref_map:
    "0.15": release-0.15.0

local_repo:
  upstream_url: https://github.com/apache/hudi.git
  repo_dir: ./workspace/upstream
  worktree_dir: ./workspace/worktrees
  target_ref:
    label: "0.15"
    ref: origin/release-0.15.0
    worktree_suffix: "015"

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
    assert "prepare-bundle" in result.output
    assert "report" in result.output
    assert "review" in result.output
    assert "retry" in result.output
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
    assert "SOURCE_NOT_APPLICABLE" in result.output
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


def test_report_writes_configured_report_directory_for_missing_database(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)

    result = runner.invoke(app, ["--config", str(config_path), "report"])

    assert result.exit_code == 0
    assert (tmp_path / "reports" / "backport-candidates.md").is_file()
    assert (tmp_path / "reports" / "inconclusive.md").is_file()
    assert (tmp_path / "reports" / "discarded.jsonl").is_file()
    assert (tmp_path / "reports" / "full-audit.jsonl").is_file()
    assert "Generated reports" in result.output


def test_review_records_status_and_comment_for_saved_pr(tmp_path: Path) -> None:
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
            "review",
            "--pr",
            "12345",
            "--status",
            "accepted_for_backport",
            "--comment",
            "Relevant to private fork",
        ],
    )

    assert result.exit_code == 0
    assert "Recorded human review for #12345: accepted_for_backport" in result.output
    with connect(sqlite_path) as connection:
        row = connection.execute(
            """
            SELECT status, reviewer, comment
            FROM human_reviews
            """
        ).fetchone()

    assert row == ("accepted_for_backport", None, "Relevant to private fork")


def test_review_rejects_invalid_pr_number(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "review",
            "--pr",
            "0",
            "--status",
            "rejected",
        ],
    )

    assert result.exit_code != 0
    assert "pr must be a positive integer" in result.output


def test_review_rejects_invalid_status(tmp_path: Path) -> None:
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
            "review",
            "--pr",
            "12345",
            "--status",
            "needs_review",
        ],
    )

    assert result.exit_code != 0
    assert "status must be one of" in result.output


def test_review_rejects_missing_pr(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "review",
            "--pr",
            "12345",
            "--status",
            "rejected",
        ],
    )

    assert result.exit_code != 0
    assert "No saved PR found for #12345" in result.output


def test_review_status_appears_in_inspect_and_report(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, with_analysis=True, status="REPORTABLE")

    review_result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "review",
            "--pr",
            "12345",
            "--status",
            "backported",
            "--comment",
            "Applied internally",
        ],
    )
    inspect_result = runner.invoke(
        app,
        ["--config", str(config_path), "inspect", "--pr", "12345"],
    )
    report_result = runner.invoke(app, ["--config", str(config_path), "report"])

    assert review_result.exit_code == 0
    assert inspect_result.exit_code == 0
    assert "backported" in inspect_result.output
    assert "Applied internally" in inspect_result.output
    assert "Reviewer" in inspect_result.output
    assert report_result.exit_code == 0

    discarded = (tmp_path / "reports" / "discarded.jsonl").read_text(
        encoding="utf-8",
    )
    audit = (tmp_path / "reports" / "full-audit.jsonl").read_text(
        encoding="utf-8",
    )
    assert '"status": "backported"' in discarded
    assert '"status": "backported"' in audit
    assert '"reviewer": null' in audit


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
    assert "Use --dry-run or --pr" in result.output


def test_analyze_pr_invokes_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)
    calls = []

    def fake_analyze_one_pr(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            run_id="run-1",
            codex_result=SimpleNamespace(exit_code=0, timed_out=False),
        )

    monkeypatch.setattr("backport_harness.main.analyze_one_pr", fake_analyze_one_pr)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["pr_number"] == 12345
    assert "Analyzed PR #12345 in run run-1" in result.output
    assert "exit=0" in result.output
    assert "timed_out=False" in result.output


def test_analyze_pr_rejects_invalid_pr(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--pr",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_analyze_pr_cannot_be_combined_with_dry_run(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "analyze",
            "--pr",
            "12345",
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "cannot be combined" in result.output


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


def test_recover_stale_reports_missing_database(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)

    result = runner.invoke(app, ["--config", str(config_path), "recover-stale"])

    assert result.exit_code == 0
    assert "Recovered 0 stale Codex run(s)." in result.output


def test_recover_stale_uses_configured_default_timeout(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path)
    locked_at = datetime.now(timezone.utc) - timedelta(hours=3)
    _mark_pr_running(sqlite_path, locked_at=locked_at)

    result = runner.invoke(app, ["--config", str(config_path), "recover-stale"])

    with connect(sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, locked_at, locked_by, last_error
            FROM analysis_queue
            """
        ).fetchone()

    assert result.exit_code == 0
    assert "Recovered 1 stale Codex run(s)." in result.output
    assert queue_row[0:3] == ("NEEDS_RETRY", None, None)
    assert "7200 second stale timeout" in queue_row[3]


def test_recover_stale_older_than_hours_overrides_configured_timeout(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path)
    locked_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    _mark_pr_running(sqlite_path, locked_at=locked_at)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "recover-stale",
            "--older-than-hours",
            "1",
        ],
    )

    with connect(sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, locked_at, locked_by, last_error
            FROM analysis_queue
            """
        ).fetchone()

    assert result.exit_code == 0
    assert "Recovered 1 stale Codex run(s)." in result.output
    assert queue_row[0:3] == ("NEEDS_RETRY", None, None)
    assert "3600 second stale timeout" in queue_row[3]


def test_recover_stale_keeps_non_stale_rows_running(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path)
    locked_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    _mark_pr_running(sqlite_path, locked_at=locked_at)

    result = runner.invoke(app, ["--config", str(config_path), "recover-stale"])

    with connect(sqlite_path) as connection:
        queue_row = connection.execute(
            """
            SELECT status, locked_at, locked_by, last_error
            FROM analysis_queue
            """
        ).fetchone()

    assert result.exit_code == 0
    assert "Recovered 0 stale Codex run(s)." in result.output
    assert queue_row == ("CODEX_RUNNING", locked_at.isoformat(), "test-worker", None)


def test_recover_stale_rejects_invalid_older_than_hours(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "recover-stale",
            "--older-than-hours",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive" in result.output


def test_retry_by_needs_retry_status(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, status="NEEDS_RETRY")

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "retry",
            "--status",
            "NEEDS_RETRY",
            "--limit",
            "3",
        ],
    )

    with connect(sqlite_path) as connection:
        row = connection.execute("SELECT status, attempts FROM analysis_queue").fetchone()

    assert result.exit_code == 0
    assert "Retried 1 PR(s)." in result.output
    assert row == ("QUEUED_FOR_ANALYSIS", 0)


def test_retry_by_failed_infra_status(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, status="FAILED_INFRA")

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "retry",
            "--status",
            "FAILED_INFRA",
            "--limit",
            "3",
        ],
    )

    with connect(sqlite_path) as connection:
        row = connection.execute("SELECT status FROM analysis_queue").fetchone()

    assert result.exit_code == 0
    assert "Retried 1 PR(s)." in result.output
    assert row == ("QUEUED_FOR_ANALYSIS",)


def test_retry_by_pr(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, status="NEEDS_RETRY")

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "retry",
            "--pr",
            "12345",
        ],
    )

    with connect(sqlite_path) as connection:
        row = connection.execute("SELECT status FROM analysis_queue").fetchone()

    assert result.exit_code == 0
    assert "Retried 1 PR(s)." in result.output
    assert row == ("QUEUED_FOR_ANALYSIS",)


@pytest.mark.parametrize(
    "args",
    [
        ["retry"],
        ["retry", "--pr", "12345", "--status", "NEEDS_RETRY"],
        ["retry", "--pr", "12345", "--limit", "3"],
    ],
)
def test_retry_rejects_invalid_selector_combinations(
    tmp_path: Path,
    args: list[str],
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(app, ["--config", str(config_path), *args])

    assert result.exit_code != 0
    assert "selector" in result.output or "cannot be combined" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["retry", "--pr", "0"],
        ["retry", "--status", "NEEDS_RETRY", "--limit", "0"],
    ],
)
def test_retry_rejects_invalid_positive_values(
    tmp_path: Path,
    args: list[str],
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(app, ["--config", str(config_path), *args])

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_retry_rejects_bulk_inconclusive(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)
    init_database(sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "retry",
            "--status",
            "INCONCLUSIVE",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code != 0
    assert "INCONCLUSIVE" in result.output
    assert "--pr" in result.output


def test_retry_reports_missing_database(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "backport_harness.sqlite3"
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path, sqlite_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "retry",
            "--status",
            "NEEDS_RETRY",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert "Retried 0 PR(s)." in result.output


def test_prepare_command_passes_pr_to_worktree_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    worktree_path = tmp_path / "workspace" / "worktrees" / "pr-12345-015"
    write_valid_config(config_path)
    calls = []

    def fake_prepare_target_worktree(config, *, pr_number):
        calls.append((config, pr_number))
        return worktree_path

    monkeypatch.setattr(
        "backport_harness.main.prepare_target_worktree",
        fake_prepare_target_worktree,
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

    def fake_prepare_target_worktree(config, *, pr_number):
        raise RuntimeError("git failed")

    monkeypatch.setattr(
        "backport_harness.main.prepare_target_worktree",
        fake_prepare_target_worktree,
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


def test_prepare_bundle_command_passes_pr_to_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    task_dir = tmp_path / "workspace" / "tasks" / "pr-12345"
    write_valid_config(config_path)
    calls = []

    def fake_build_task_bundle(**kwargs):
        calls.append(kwargs)
        return TaskBundle(
            pr_number=12345,
            task_dir=task_dir,
            worktree_path=tmp_path / "workspace" / "worktrees" / "pr-12345-015",
            pr_json_path=task_dir / "pr.json",
            files_changed_json_path=task_dir / "files_changed.json",
            diff_path=task_dir / "pr.diff",
            instructions_path=task_dir / "instructions.md",
            output_dir=task_dir / "output",
            logs_dir=task_dir / "output" / "logs",
            patches_dir=task_dir / "output" / "patches",
        )

    monkeypatch.setattr("backport_harness.main.build_task_bundle", fake_build_task_bundle)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare-bundle",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["pr_number"] == 12345
    assert str(task_dir) in result.output


def test_prepare_bundle_command_rejects_invalid_pr(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare-bundle",
            "--pr",
            "0",
        ],
    )

    assert result.exit_code != 0
    assert "positive integer" in result.output


def test_prepare_bundle_command_reports_builder_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_valid_config(config_path)

    def fake_build_task_bundle(**kwargs):
        raise RuntimeError("bundle failed")

    monkeypatch.setattr("backport_harness.main.build_task_bundle", fake_build_task_bundle)

    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "prepare-bundle",
            "--pr",
            "12345",
        ],
    )

    assert result.exit_code != 0
    assert "bundle failed" in result.output


def _insert_saved_pr(
    sqlite_path: Path,
    *,
    with_file: bool = False,
    with_analysis: bool = False,
    with_failed_analysis: bool = False,
    status: str = "QUEUED_FOR_ANALYSIS",
    attempts: int = 0,
) -> None:
    with connect(sqlite_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO prs(
                github_pr_number,
                github_pr_url,
                title,
                upstream_branch,
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
                status,
                100,
                attempts,
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


def _mark_pr_running(sqlite_path: Path, *, locked_at: datetime) -> None:
    with connect(sqlite_path) as connection:
        connection.execute(
            """
            UPDATE analysis_queue
            SET status = ?,
                locked_at = ?,
                locked_by = ?
            """,
            ("CODEX_RUNNING", locked_at.isoformat(), "test-worker"),
        )


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
            applies_to_target_ref,
            reason,
            human_action,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            analysis_run_id,
            "SOURCE_NOT_APPLICABLE",
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
