from pathlib import Path

from typer.testing import CliRunner

from backport_harness import __version__
from backport_harness.main import app


runner = CliRunner()


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
    config_path.write_text("github:\n  owner: apache\n", encoding="utf-8")

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
    config_path.write_text(
        f"storage:\n  sqlite_path: {sqlite_path}\n",
        encoding="utf-8",
    )

    first_result = runner.invoke(app, ["--config", str(config_path), "db", "init"])
    second_result = runner.invoke(app, ["--config", str(config_path), "db", "init"])

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert sqlite_path.is_file()
