from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


GITHUB_CREDENTIAL_ENV_VARS = {
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GH_ENTERPRISE_TOKEN",
}


@dataclass(frozen=True)
class CodexRunRequest:
    prompt: str
    cwd: Path
    timeout_seconds: int
    output_result_path: Path
    command: str = "codex"
    extra_env: dict[str, str] = field(default_factory=dict)
    github_token_env: str | None = None
    reasoning_effort: str = "medium"


@dataclass(frozen=True)
class CodexRunResult:
    session_id: str | None
    exit_code: int | None
    timed_out: bool
    stdout_log_path: Path
    stderr_log_path: Path
    last_message_path: Path | None
    started_at: str
    finished_at: str


def run_codex(request: CodexRunRequest) -> CodexRunResult:
    started_at = _utc_now()
    output_dir = request.output_result_path.parent
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log_path = logs_dir / "codex-stdout.log"
    stderr_log_path = logs_dir / "codex-stderr.log"
    final_last_message_path = output_dir / "last-message.jsonl"

    with tempfile.TemporaryDirectory(prefix="backport-codex-") as temp_dir:
        temp_last_message_path = Path(temp_dir) / "last-message.jsonl"
        process = subprocess.Popen(
            [
                request.command,
                "exec",
                "-C",
                str(request.cwd),
                "--dangerously-bypass-approvals-and-sandbox",
                "--json",
                "-o",
                str(temp_last_message_path),
                "-c",
                f'model_reasoning_effort="{request.reasoning_effort}"',
                request.prompt,
            ],
            cwd=request.cwd,
            env=_codex_env(request),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process)
            stdout, stderr = process.communicate()

        stdout_log_path.write_text(stdout or "", encoding="utf-8")
        stderr_log_path.write_text(stderr or "", encoding="utf-8")

        copied_last_message_path = None
        if temp_last_message_path.exists():
            shutil.copyfile(temp_last_message_path, final_last_message_path)
            copied_last_message_path = final_last_message_path

        finished_at = _utc_now()
        return CodexRunResult(
            session_id=_parse_session_id(copied_last_message_path),
            exit_code=process.returncode,
            timed_out=timed_out,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            last_message_path=copied_last_message_path,
            started_at=started_at,
            finished_at=finished_at,
        )


def _codex_env(request: CodexRunRequest) -> dict[str, str]:
    env = os.environ.copy()
    env.update(request.extra_env)
    blocked = set(GITHUB_CREDENTIAL_ENV_VARS)
    if request.github_token_env:
        blocked.add(request.github_token_env)
    for key in blocked:
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _terminate_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        for _ in range(10):
            if process.poll() is not None:
                return
            time.sleep(0.1)
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _parse_session_id(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None

    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        found = _find_uuid(payload)
        if found is not None:
            return found
    return None


def _find_uuid(value: object) -> str | None:
    if isinstance(value, str):
        try:
            return str(uuid.UUID(value))
        except ValueError:
            return None
    if isinstance(value, dict):
        for nested in value.values():
            found = _find_uuid(nested)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_uuid(nested)
            if found is not None:
                return found
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
