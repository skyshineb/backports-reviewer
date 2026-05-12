from pathlib import Path

from typer.testing import CliRunner

from backport_harness import __version__
from backport_harness.main import app


runner = CliRunner()


def test_help_shows_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
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

