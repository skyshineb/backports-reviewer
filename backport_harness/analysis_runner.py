from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass

from backport_harness.codex_runner import CodexRunRequest, CodexRunResult, run_codex
from backport_harness.config import HarnessConfig
from backport_harness.storage import connect, finish_analysis_run, start_analysis_run
from backport_harness.task_builder import build_task_bundle


@dataclass(frozen=True)
class AnalyzeOneResult:
    pr_number: int
    run_id: str
    task_dir: str
    codex_result: CodexRunResult


def analyze_one_pr(
    *,
    config: HarnessConfig,
    pr_number: int,
) -> AnalyzeOneResult:
    bundle = build_task_bundle(
        config=config,
        sqlite_path=config.storage.sqlite_path,
        pr_number=pr_number,
    )
    run_id = str(uuid.uuid4())
    locked_by = f"backport-harness@{socket.gethostname()}"

    with connect(config.storage.sqlite_path) as connection:
        analysis_start = start_analysis_run(
            connection,
            pr_number=pr_number,
            run_id=run_id,
            task_dir=bundle.task_dir,
            locked_by=locked_by,
        )

    prompt = bundle.instructions_path.read_text(encoding="utf-8")
    codex_result = run_codex(
        CodexRunRequest(
            prompt=prompt,
            cwd=bundle.task_dir,
            timeout_seconds=config.codex.timeout_seconds,
            output_result_path=bundle.task_dir / config.codex.result_file,
            command=config.codex.command,
            github_token_env=config.github.token_env,
        )
    )

    with connect(config.storage.sqlite_path) as connection:
        finish_analysis_run(
            connection,
            pr_id=analysis_start.pr_id,
            analysis_run_id=analysis_start.analysis_run_id,
            codex_exit_code=codex_result.exit_code,
            timed_out=codex_result.timed_out,
            result_json_path=bundle.task_dir / config.codex.result_file,
            notes_path=bundle.output_dir / "notes.md",
            stdout_log_path=codex_result.stdout_log_path,
            stderr_log_path=codex_result.stderr_log_path,
            attempts=analysis_start.attempts,
            max_attempts=config.codex.max_attempts_per_pr,
        )

    return AnalyzeOneResult(
        pr_number=pr_number,
        run_id=run_id,
        task_dir=str(bundle.task_dir),
        codex_result=codex_result,
    )
