from pathlib import Path

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
