from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass

from backport_harness.codex_runner import CodexRunRequest, CodexRunResult, run_codex
from backport_harness.config import HarnessConfig
from backport_harness.result_validator import ValidationOutcome, validate_codex_result_file
from backport_harness.storage import (
    connect,
    finish_analysis_run,
    finish_result_validation,
    start_analysis_run,
    store_validated_decision,
)
from backport_harness.task_builder import build_task_bundle, resolve_task_dir


@dataclass(frozen=True)
class AnalyzeOneResult:
    pr_number: int
    run_id: str
    task_dir: str
    codex_result: CodexRunResult
    validation: ValidationOutcome | None


def analyze_one_pr(
    *,
    config: HarnessConfig,
    pr_number: int,
) -> AnalyzeOneResult:
    task_dir = resolve_task_dir(config=config, pr_number=pr_number)
    run_id = str(uuid.uuid4())
    locked_by = f"backport-harness@{socket.gethostname()}"

    with connect(config.storage.sqlite_path) as connection:
        analysis_start = start_analysis_run(
            connection,
            pr_number=pr_number,
            run_id=run_id,
            task_dir=task_dir,
            locked_by=locked_by,
        )

    try:
        bundle = build_task_bundle(
            config=config,
            sqlite_path=config.storage.sqlite_path,
            pr_number=pr_number,
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
    except Exception as error:
        stdout_log_path = task_dir / "output" / "logs" / "codex-stdout.log"
        stderr_log_path = task_dir / "output" / "logs" / "codex-stderr.log"
        stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_log_path.write_text("", encoding="utf-8")
        last_error = f"Codex analysis failed before completion: {type(error).__name__}: {error}"
        stderr_log_path.write_text(last_error + "\n", encoding="utf-8")

        with connect(config.storage.sqlite_path) as connection:
            finish_analysis_run(
                connection,
                pr_id=analysis_start.pr_id,
                analysis_run_id=analysis_start.analysis_run_id,
                codex_exit_code=None,
                timed_out=False,
                result_json_path=task_dir / config.codex.result_file,
                notes_path=task_dir / "output" / "notes.md",
                stdout_log_path=stdout_log_path,
                stderr_log_path=stderr_log_path,
                attempts=analysis_start.attempts,
                max_attempts=config.codex.max_attempts_per_pr,
                last_error=last_error,
            )
        raise RuntimeError(last_error) from error

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

    validation = None
    if codex_result.exit_code == 0 and not codex_result.timed_out:
        validation = validate_codex_result_file(
            task_dir=bundle.task_dir,
            result_path=bundle.task_dir / config.codex.result_file,
            expected_target_branch=analysis_start.target_branch,
        )
        with connect(config.storage.sqlite_path) as connection:
            finish_result_validation(
                connection,
                pr_id=analysis_start.pr_id,
                analysis_run_id=analysis_start.analysis_run_id,
                valid=validation.valid,
                attempts=analysis_start.attempts,
                max_attempts=config.codex.max_attempts_per_pr,
                last_error=None if validation.valid else validation.summary,
            )
            if validation.valid and validation.result is not None:
                store_validated_decision(
                    connection,
                    pr_id=analysis_start.pr_id,
                    analysis_run_id=analysis_start.analysis_run_id,
                    result=validation.result,
                )
        if not validation.valid:
            raise RuntimeError(f"Codex result failed validation: {validation.summary}")

    return AnalyzeOneResult(
        pr_number=pr_number,
        run_id=run_id,
        task_dir=str(bundle.task_dir),
        codex_result=codex_result,
        validation=validation,
    )
