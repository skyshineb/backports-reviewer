from __future__ import annotations

import subprocess
from pathlib import Path

from backport_harness.codex_runner import CodexRunRequest, run_codex


class FakeProcess:
    def __init__(self, *, returncode=0, timeout=False):
        self.pid = 123
        self.returncode = returncode
        self.timeout = timeout
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)
        return '{"session":{"id":"12345678-1234-5678-1234-567812345678"}}\n', "stderr\n"

    def poll(self):
        return self.returncode


def test_run_codex_invokes_expected_argv_and_writes_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        last_message_path = Path(args[args.index("-o") + 1])
        last_message_path.write_text(
            '{"nested":{"session_id":"12345678-1234-5678-1234-567812345678"}}\n',
            encoding="utf-8",
        )
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")

    result = run_codex(
        CodexRunRequest(
            prompt="do work",
            cwd=tmp_path,
            timeout_seconds=30,
            output_result_path=tmp_path / "output" / "codex_result.json",
            command="codex",
            github_token_env="GITHUB_TOKEN",
        )
    )

    args, kwargs = calls[0]
    assert args[:8] == [
        "codex",
        "exec",
        "-C",
        str(tmp_path),
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
        "-o",
        args[7],
    ]
    assert args[8:10] == ["-c", 'model_reasoning_effort="medium"']
    assert args[-1] == "do work"
    assert kwargs["cwd"] == tmp_path
    assert kwargs["start_new_session"] is True
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert "GITHUB_TOKEN" not in kwargs["env"]
    assert kwargs["env"]["OPENAI_API_KEY"] == "provider-secret"
    assert result.session_id == "12345678-1234-5678-1234-567812345678"
    assert result.stdout_log_path.read_text(encoding="utf-8").startswith('{"session"')
    assert result.stderr_log_path.read_text(encoding="utf-8") == "stderr\n"
    assert result.last_message_path is not None
    assert result.last_message_path.name == "last-message.jsonl"


def test_run_codex_uses_configured_reasoning_effort(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    run_codex(
        CodexRunRequest(
            prompt="do work",
            cwd=tmp_path,
            timeout_seconds=30,
            output_result_path=tmp_path / "output" / "codex_result.json",
            reasoning_effort="high",
        )
    )

    args = calls[0][0]
    assert args[args.index("-c") + 1] == 'model_reasoning_effort="high"'


def test_run_codex_timeout_signals_process_group(tmp_path: Path, monkeypatch) -> None:
    signals = []

    def fake_popen(args, **kwargs):
        return FakeProcess(returncode=None, timeout=True)

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("os.killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    result = run_codex(
        CodexRunRequest(
            prompt="do work",
            cwd=tmp_path,
            timeout_seconds=1,
            output_result_path=tmp_path / "output" / "codex_result.json",
        )
    )

    assert result.timed_out is True
    assert signals


def test_run_codex_strips_blocked_credentials_from_extra_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")

    run_codex(
        CodexRunRequest(
            prompt="do work",
            cwd=tmp_path,
            timeout_seconds=30,
            output_result_path=tmp_path / "output" / "codex_result.json",
            extra_env={
                "GITHUB_TOKEN": "extra-secret",
                "GH_TOKEN": "extra-secret",
                "CUSTOM_GITHUB_TOKEN": "extra-secret",
                "OPENAI_API_KEY": "provider-secret",
            },
            github_token_env="CUSTOM_GITHUB_TOKEN",
        )
    )

    env = calls[0][1]["env"]
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "CUSTOM_GITHUB_TOKEN" not in env
    assert env["OPENAI_API_KEY"] == "provider-secret"
