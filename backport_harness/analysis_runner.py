from __future__ import annotations

import socket
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from backport_harness.codex_runner import CodexRunRequest, CodexRunResult, run_codex
from backport_harness.config import HarnessConfig
from backport_harness.result_validator import ValidationOutcome, validate_codex_result_file
from backport_harness.storage import (
    AnalysisCandidate,
    AnalysisQueueSummary,
    connect,
    finish_analysis_run,
    finish_result_validation,
    get_analysis_queue_summary,
    select_analysis_candidates,
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


@dataclass(frozen=True)
class AnalyzeBatchItemResult:
    pr_number: int
    title: str
    upstream_branch: str
    initial_queue_status: str
    final_queue_status: str | None
    outcome: str
    run_id: str | None
    codex_exit_code: int | None
    timed_out: bool | None
    error: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class AnalyzeBatchResult:
    selected_count: int
    processed_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    elapsed_seconds: float
    stop_reason: str
    items: list[AnalyzeBatchItemResult]


AnalyzeOneCallable = Callable[..., AnalyzeOneResult]
ClockCallable = Callable[[], float]


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
                reasoning_effort=config.codex.reasoning_effort,
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
            expected_upstream_branch=analysis_start.upstream_branch,
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


def analyze_pr_batch(
    *,
    config: HarnessConfig,
    limit: int,
    max_runtime_minutes: float | None = None,
    fail_fast: bool = False,
    analyze_one: AnalyzeOneCallable | None = None,
    clock: ClockCallable | None = None,
) -> AnalyzeBatchResult:
    if limit <= 0:
        raise ValueError("limit must be positive.")
    if max_runtime_minutes is not None and max_runtime_minutes <= 0:
        raise ValueError("max_runtime_minutes must be positive.")

    clock = clock or time.monotonic
    start_time = clock()
    max_runtime_seconds = (
        max_runtime_minutes * 60.0 if max_runtime_minutes is not None else None
    )
    one_pr_runner = analyze_one or _call_analyze_one_pr

    if not config.storage.sqlite_path.exists():
        elapsed = max(0.0, clock() - start_time)
        return AnalyzeBatchResult(
            selected_count=0,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
            elapsed_seconds=elapsed,
            stop_reason="no candidates",
            items=[],
        )

    with connect(config.storage.sqlite_path) as connection:
        candidates = select_analysis_candidates(connection, limit=limit)

    items: list[AnalyzeBatchItemResult] = []
    stop_reason = "selected candidates exhausted"
    if not candidates:
        elapsed = max(0.0, clock() - start_time)
        return AnalyzeBatchResult(
            selected_count=0,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
            elapsed_seconds=elapsed,
            stop_reason="no candidates",
            items=[],
        )

    for index, candidate in enumerate(candidates):
        elapsed = clock() - start_time
        if max_runtime_seconds is not None and elapsed >= max_runtime_seconds:
            stop_reason = "max runtime reached"
            items.extend(
                _skipped_batch_items(
                    candidates[index:],
                    reason="not started because max runtime was reached",
                )
            )
            break

        try:
            result = one_pr_runner(
                config=config,
                pr_number=candidate.github_pr_number,
            )
        except KeyboardInterrupt:
            queue_summary = _queue_summary_for_candidate(config, candidate)
            items.append(
                _failed_batch_item(
                    candidate=candidate,
                    queue_summary=queue_summary,
                    error=(
                        "Interrupted during Codex analysis. If the queue row remains "
                        "CODEX_RUNNING, run recover-stale before retrying."
                    ),
                    run_id=None,
                    codex_exit_code=None,
                    timed_out=None,
                    outcome="interrupted",
                )
            )
            stop_reason = "interrupted during analysis"
            items.extend(
                _skipped_batch_items(
                    candidates[index + 1 :],
                    reason="not started because analysis was interrupted",
                )
            )
            break
        except Exception as error:
            queue_summary = _queue_summary_for_candidate(config, candidate)
            items.append(
                _failed_batch_item(
                    candidate=candidate,
                    queue_summary=queue_summary,
                    error=f"{type(error).__name__}: {error}",
                    run_id=None,
                    codex_exit_code=None,
                    timed_out=None,
                )
            )
            if fail_fast:
                stop_reason = f"fail-fast after PR #{candidate.github_pr_number}"
                items.extend(
                    _skipped_batch_items(
                        candidates[index + 1 :],
                        reason="not started because fail-fast stopped the batch",
                    )
                )
                break
            continue

        queue_summary = _queue_summary_for_candidate(config, candidate)
        item_failed = _analysis_result_failed(
            result=result,
            queue_summary=queue_summary,
        )
        if item_failed:
            items.append(
                _failed_batch_item(
                    candidate=candidate,
                    queue_summary=queue_summary,
                    error=_failure_message(result=result, queue_summary=queue_summary),
                    run_id=result.run_id,
                    codex_exit_code=result.codex_result.exit_code,
                    timed_out=result.codex_result.timed_out,
                )
            )
            if fail_fast:
                stop_reason = f"fail-fast after PR #{candidate.github_pr_number}"
                items.extend(
                    _skipped_batch_items(
                        candidates[index + 1 :],
                        reason="not started because fail-fast stopped the batch",
                    )
                )
                break
            continue

        items.append(
            AnalyzeBatchItemResult(
                pr_number=candidate.github_pr_number,
                title=candidate.title,
                upstream_branch=candidate.upstream_branch,
                initial_queue_status=candidate.queue_status,
                final_queue_status=_queue_status(queue_summary),
                outcome="succeeded",
                run_id=result.run_id,
                codex_exit_code=result.codex_result.exit_code,
                timed_out=result.codex_result.timed_out,
                error=None,
                skip_reason=None,
            )
        )

    processed_count = sum(1 for item in items if item.outcome != "skipped")
    failed_count = sum(
        1 for item in items if item.outcome in {"failed", "interrupted"}
    )
    skipped_count = sum(1 for item in items if item.outcome == "skipped")
    succeeded_count = sum(1 for item in items if item.outcome == "succeeded")
    elapsed = max(0.0, clock() - start_time)
    return AnalyzeBatchResult(
        selected_count=len(candidates),
        processed_count=processed_count,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        elapsed_seconds=elapsed,
        stop_reason=stop_reason,
        items=items,
    )


def _call_analyze_one_pr(
    *,
    config: HarnessConfig,
    pr_number: int,
) -> AnalyzeOneResult:
    return analyze_one_pr(config=config, pr_number=pr_number)


def _queue_summary_for_candidate(
    config: HarnessConfig,
    candidate: AnalysisCandidate,
) -> AnalysisQueueSummary | None:
    with connect(config.storage.sqlite_path) as connection:
        return get_analysis_queue_summary(
            connection,
            pr_number=candidate.github_pr_number,
            upstream_branch=candidate.upstream_branch,
        )


def _analysis_result_failed(
    *,
    result: AnalyzeOneResult,
    queue_summary: AnalysisQueueSummary | None,
) -> bool:
    if result.codex_result.timed_out or result.codex_result.exit_code != 0:
        return True
    return _queue_status(queue_summary) in {"NEEDS_RETRY", "FAILED_INFRA"}


def _failure_message(
    *,
    result: AnalyzeOneResult,
    queue_summary: AnalysisQueueSummary | None,
) -> str:
    if queue_summary is not None and queue_summary.last_error:
        return queue_summary.last_error
    if result.codex_result.timed_out:
        return "Codex timed out."
    return f"Codex exited with {result.codex_result.exit_code}."


def _failed_batch_item(
    *,
    candidate: AnalysisCandidate,
    queue_summary: AnalysisQueueSummary | None,
    error: str,
    run_id: str | None,
    codex_exit_code: int | None,
    timed_out: bool | None,
    outcome: str = "failed",
) -> AnalyzeBatchItemResult:
    return AnalyzeBatchItemResult(
        pr_number=candidate.github_pr_number,
        title=candidate.title,
        upstream_branch=candidate.upstream_branch,
        initial_queue_status=candidate.queue_status,
        final_queue_status=_queue_status(queue_summary),
        outcome=outcome,
        run_id=run_id,
        codex_exit_code=codex_exit_code,
        timed_out=timed_out,
        error=error,
        skip_reason=None,
    )


def _skipped_batch_items(
    candidates: list[AnalysisCandidate],
    *,
    reason: str,
) -> list[AnalyzeBatchItemResult]:
    return [
        AnalyzeBatchItemResult(
            pr_number=candidate.github_pr_number,
            title=candidate.title,
            upstream_branch=candidate.upstream_branch,
            initial_queue_status=candidate.queue_status,
            final_queue_status=None,
            outcome="skipped",
            run_id=None,
            codex_exit_code=None,
            timed_out=None,
            error=None,
            skip_reason=reason,
        )
        for candidate in candidates
    ]


def _queue_status(queue_summary: AnalysisQueueSummary | None) -> str | None:
    if queue_summary is None:
        return None
    return queue_summary.queue_status
