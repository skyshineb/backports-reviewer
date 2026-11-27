from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from backport_harness.codex_runner import _terminate_process_group
from backport_harness.config import DEFAULT_CODEX_TIMEOUT_SECONDS
from backport_harness.dashboard.codex import (
    Adaptation, CodexError, JobCanceled, Review, Snapshot, task_input, validate_result,
)

AUTH_SETTINGS = ('cli_auth_credentials_store="auto"', 'model_provider="openai"')
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "shell_snapshot", "apps", "plugins", "hooks",
    "browser_use", "computer_use", "code_mode", "view_image", "image_generation",
    "skill_search", "skill_mcp_dependency_install", "multi_agent", "multi_agent_v2",
    "request_permissions_tool", "goals",
)
CODEX_ENVIRONMENT = (
    "PATH", "HOME", "CODEX_HOME", "USER", "LOGNAME", "LANG", "LC_ALL",
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "DBUS_SESSION_BUS_ADDRESS",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "CODEX_CA_CERTIFICATE",
)
MAX_RESULT_BYTES = 1_500_000


def cli_environment() -> dict[str, str]:
    env = {name: os.environ[name] for name in CODEX_ENVIRONMENT if name in os.environ}
    env["LC_ALL"] = "C.UTF-8"
    return env


class StaticCliCodex:
    def __init__(
        self,
        command: str = "codex",
        model: str | None = None,
        timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
    ) -> None:
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._auth_lock = threading.Lock()
        self._auth_checked = 0.0
        self._auth_result: tuple[str | None, str | None] = (None, None)

    @property
    def available(self) -> bool:
        command, problem = self._preflight()
        return bool(command and not problem)

    def _preflight(self, *, refresh: bool = False) -> tuple[str | None, str | None]:
        with self._auth_lock:
            now = time.monotonic()
            if refresh or not self._auth_checked or now - self._auth_checked >= 10:
                self._auth_result = self._check_login()
                self._auth_checked = now
            return self._auth_result

    def _check_login(self) -> tuple[str | None, str | None]:
        exe = shutil.which(self.command)
        if not exe:
            return None, "Install the Codex CLI and make it available on the dashboard's PATH."
        command = [str(Path(exe).absolute()), "login", "status"]
        for setting in AUTH_SETTINGS:
            command.extend(("-c", setting))
        try:
            with tempfile.TemporaryDirectory(prefix="backport-codex-login-") as directory:
                result = subprocess.run(command, cwd=directory, env=cli_environment(),
                                        stdin=subprocess.DEVNULL, capture_output=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            return exe, "Could not check the Codex login. Run codex login status."
        status = result.stdout + result.stderr
        if result.returncode or b"Logged in using ChatGPT" not in status:
            return exe, "Run codex login and sign in with ChatGPT as the dashboard user."
        return str(Path(exe).absolute()), None

    def _command(self, exe: str, directory: Path, snapshot: Snapshot) -> list[str]:
        mcp_args = json.dumps(
            ["-I", "-m", "backport_harness.dashboard.snapshot_mcp", str(snapshot.repo), snapshot.sha],
            ensure_ascii=False,
        )
        server = (
            "{ command = " + json.dumps(sys.executable, ensure_ascii=False) + ", args = " + mcp_args
            + ', required = true, enabled_tools = ["list_paths", "read_file"] }'
        )
        settings = (
            *AUTH_SETTINGS,
            'model_reasoning_effort="high"',
            'approval_policy="never"',
            'default_permissions="backport-snapshot"',
            'permissions.backport-snapshot.filesystem={":workspace_roots"={"."="read"}}',
            'permissions.backport-snapshot.network={enabled=false}',
            'web_search="disabled"',
            'project_doc_max_bytes=0',
            'skills.bundled.enabled=false',
            'skills.include_instructions=false',
            'memories.use_memories=false',
            'memories.generate_memories=false',
            'analytics.enabled=false',
            'history.persistence="none"',
            f"mcp_servers={{backport_snapshot={server}}}",
        )
        argv = [
            exe, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
            "--strict-config", "--cd", str(directory), "--json",
            "--output-schema", str(directory / "schema.json"),
            "--output-last-message", str(directory / "result.json"),
        ]
        for feature in DISABLED_FEATURES:
            argv.extend(("--disable", feature))
        for setting in settings:
            argv.extend(("-c", setting))
        if self.model:
            argv.extend(("--model", self.model))
        return [*argv, "-"]

    def run(
        self,
        snapshot: Snapshot,
        upstream_diff: str,
        prompt: str,
        *,
        adapt: bool,
        canceled: Callable[[], bool],
    ) -> Review | Adaptation:
        if canceled():
            raise JobCanceled()
        exe, problem = self._preflight(refresh=True)
        if not exe or problem:
            raise CodexError(problem or "Codex CLI is unavailable.")
        directives, data = task_input(snapshot, upstream_diff, prompt, adapt=adapt)
        inputs = f"{directives}\n\nUse the backport_snapshot tools to inspect the pinned source.\n\n{data}"
        shape = Adaptation if adapt else Review

        with tempfile.TemporaryDirectory(prefix="backport-codex-cli-") as temp:
            directory = Path(temp)
            (directory / "schema.json").write_text(json.dumps(shape.model_json_schema()), encoding="utf-8")
            self._execute(self._command(exe, directory, snapshot), directory, inputs.encode(), canceled)
            try:
                with (directory / "result.json").open("rb") as result:
                    text = result.read(MAX_RESULT_BYTES + 1)
            except OSError as error:
                raise CodexError("Codex CLI did not produce a result.") from error
            if len(text) > MAX_RESULT_BYTES:
                raise CodexError("The Codex result exceeds the size limit.")
            return validate_result(text, shape, snapshot)

    def _execute(self, command: list[str], directory: Path, inputs: bytes, canceled: Callable[[], bool]) -> None:
        if canceled():
            raise JobCanceled()
        try:
            process = subprocess.Popen(
                command, cwd=directory, env=cli_environment(), start_new_session=True,
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise CodexError("Could not start Codex CLI.") from error
        deadline = time.monotonic() + self.timeout_seconds
        pending_input: bytes | None = inputs
        with process:
            while True:
                remaining = deadline - time.monotonic()
                interrupted = canceled()
                if interrupted or remaining <= 0:
                    _terminate_process_group(process)
                    if interrupted:
                        raise JobCanceled()
                    raise CodexError("Codex CLI timed out.")
                try:
                    process.communicate(input=pending_input, timeout=min(remaining, 0.5))
                    break
                except subprocess.TimeoutExpired:
                    pending_input = None
            if canceled():
                raise JobCanceled()
            if process.returncode:
                raise CodexError(
                    f"Codex CLI exited with code {process.returncode}. Check the CLI version and codex login status."
                )
