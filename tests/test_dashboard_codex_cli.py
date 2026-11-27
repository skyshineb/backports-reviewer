import json
import subprocess
import sys
import threading

import pytest
from typer.testing import CliRunner

from backport_harness.dashboard.codex import CodexError, JobCanceled, Snapshot
from backport_harness.dashboard.codex_cli import StaticCliCodex
from backport_harness.dashboard.models import CodexBackendName
from backport_harness.main import app
from test_dashboard_git import repositories


@pytest.fixture
def snapshot(repositories):
    _, _, workspace, settings, _ = repositories
    sha = workspace.snapshot(1, settings)
    return Snapshot(workspace.mirror(1), sha)


def executable(tmp_path, code):
    command = tmp_path / "codex-fake"
    command.write_text(f"#!{sys.executable}\n{code}\n", encoding="utf-8")
    command.chmod(0o700)
    return str(command)


CHATGPT_LOGIN = """
if sys.argv[1:3] == ["login", "status"]:
    print("Logged in using ChatGPT")
    sys.exit(0)
"""


def test_cli_reuses_login_and_validates_result(tmp_path, snapshot, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "synthetic-secret")
    command = executable(tmp_path, f"""
import json
import os
import sys
from pathlib import Path

assert all(key not in os.environ for key in
    ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "GITHUB_TOKEN"))
{CHATGPT_LOGIN}
args = sys.argv[1:]
assert args[0] == "exec"
assert "--ignore-user-config" in args and "--ephemeral" in args
assert "--strict-config" in args and "--dangerously-bypass-approvals-and-sandbox" not in args
assert 'model_reasoning_effort="high"' in args
assert 'approval_policy="never"' in args
assert 'web_search="disabled"' in args
disabled = {{args[index + 1] for index, arg in enumerate(args) if arg == "--disable"}}
assert {{"shell_tool", "unified_exec", "computer_use", "browser_use", "hooks", "plugins"}} <= disabled
assert args[-1] == "-"
assert str(Path.cwd()) == args[args.index("--cd") + 1]
assert "test instructions" in sys.stdin.read()
assert "test instructions" not in " ".join(args)
schema = Path(args[args.index("--output-schema") + 1])
assert "severity" in json.loads(schema.read_text())["properties"]
result = Path(args[args.index("--output-last-message") + 1])
result.write_text(json.dumps({{
    "relevance": "affected", "severity": "medium", "notes": "Pinned fork is affected.",
    "evidence": [{{"path": "conflict.txt", "line": 1}}],
}}))
""")
    cli = StaticCliCodex(command)
    assert cli.available
    result = cli.run(snapshot, "upstream diff", "test instructions", adapt=False, canceled=lambda: False)
    assert result.severity == "medium"
    assert result.evidence[0].path == "conflict.txt"


def test_cli_requires_chatgpt_session(tmp_path, snapshot):
    command = executable(tmp_path, 'print("Logged in using an API key")')
    cli = StaticCliCodex(command)
    assert not cli.available
    with pytest.raises(CodexError, match="sign in with ChatGPT"):
        cli.run(snapshot, "diff", "", adapt=False, canceled=lambda: False)


def test_cli_rejects_unreadable_evidence(tmp_path, snapshot):
    command = executable(tmp_path, f"""
import json
import sys
from pathlib import Path

{CHATGPT_LOGIN}
args = sys.argv[1:]
sys.stdin.read()
Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps({{
    "relevance": "affected", "severity": "major", "notes": "Bad evidence.",
    "evidence": [{{"path": "../outside.txt", "line": 1}}],
}}))
""")
    with pytest.raises(CodexError, match="outside the readable snapshot"):
        StaticCliCodex(command).run(snapshot, "diff", "", adapt=False, canceled=lambda: False)


def test_cli_cancellation_and_timeout(tmp_path, snapshot):
    command = executable(tmp_path, f"""
import sys
import time

{CHATGPT_LOGIN}
sys.stdin.read()
time.sleep(30)
""")
    canceled = threading.Event()
    timer = threading.Timer(0.25, canceled.set)
    timer.start()
    try:
        with pytest.raises(JobCanceled):
            StaticCliCodex(command).run(snapshot, "diff", "", adapt=False, canceled=canceled.is_set)
    finally:
        timer.cancel()
    with pytest.raises(CodexError, match="timed out"):
        StaticCliCodex(command, timeout_seconds=1).run(
            snapshot, "diff", "", adapt=True, canceled=lambda: False,
        )


def test_snapshot_mcp_only_exposes_pinned_reads(snapshot):
    requests = [
        {"method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"method": "tools/list"},
        {"method": "tools/call", "params": {"name": "read_file", "arguments": {
            "path": "conflict.txt", "start_line": 1,
        }}},
        {"method": "tools/call", "params": {"name": "read_file", "arguments": {
            "path": "../../etc/passwd", "start_line": 1,
        }}},
        {"method": "tools/call", "params": {"name": "shell", "arguments": {}}},
    ]
    payload = "".join(json.dumps(request | {"jsonrpc": "2.0", "id": idx}) + "\n"
                      for idx, request in enumerate(requests))
    result = subprocess.run(
        [sys.executable, "-I", "-m", "backport_harness.dashboard.snapshot_mcp",
         str(snapshot.repo), snapshot.sha],
        input=payload, capture_output=True, text=True, check=True, timeout=10,
    )
    initialize, tools, read, outside, shell = [json.loads(line)["result"] for line in result.stdout.splitlines()]
    assert initialize["protocolVersion"] == "2025-06-18"
    assert {tool["name"] for tool in tools["tools"]} == {"list_paths", "read_file"}
    assert json.loads(read["content"][0]["text"])["text"] == "private behavior"
    assert outside["isError"] and shell["isError"]


def test_serve_can_select_cli(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr("backport_harness.dashboard.web.serve", lambda *args, **kwargs: called.append(kwargs))
    result = CliRunner().invoke(
        app, ["--config", str(tmp_path / "missing.yaml"), "serve", "--codex-backend", "cli"],
    )
    assert result.exit_code == 0, result.output
    assert called[0]["codex_backend"] == CodexBackendName.CLI
