from pathlib import Path
from types import SimpleNamespace

import pytest

from backport_harness.git_runner import GitCommandError, run_git


def test_run_git_passes_argv_without_shell_and_disables_prompts(monkeypatch) -> None:
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: fake_run(**kwargs))

    result = run_git(["git", "status"], cwd=Path("/tmp/repo"))

    assert result.stdout == "ok\n"
    assert calls[0]["cwd"] == Path("/tmp/repo")
    assert calls[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert calls[0]["text"] is True
    assert calls[0]["capture_output"] is True
    assert calls[0]["check"] is False


def test_run_git_rejects_non_git_command() -> None:
    with pytest.raises(ValueError, match="must start with 'git'"):
        run_git(["echo", "no"])


def test_run_git_raises_on_non_zero_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="out",
            stderr="err",
        ),
    )

    with pytest.raises(GitCommandError, match="Git command failed") as error:
        run_git(["git", "status"])

    assert error.value.returncode == 1
    assert error.value.stdout == "out"
    assert error.value.stderr == "err"
