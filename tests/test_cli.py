from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from backport_harness import __version__
from backport_harness.main import app


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
