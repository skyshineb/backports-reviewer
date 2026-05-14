from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from backport_harness.config import HarnessConfig
from backport_harness.git_runner import run_git
from backport_harness.security import (
    validate_no_path_overlap,
    validate_public_path,
    validate_safe_child_path,
)
from backport_harness.storage import InspectedPullRequest, connect
from backport_harness.storage import get_pull_request_inspection
from backport_harness.worktree_manager import prepare_oss_015_worktree


class TaskBundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskBundle:
    pr_number: int
    task_dir: Path
    worktree_path: Path
    pr_json_path: Path
    files_changed_json_path: Path
    diff_path: Path
    instructions_path: Path
    output_dir: Path
    logs_dir: Path
    patches_dir: Path


def build_task_bundle(
    *,
    config: HarnessConfig,
    sqlite_path: Path,
    pr_number: int,
) -> TaskBundle:
    if pr_number < 1:
        raise ValueError("pr_number must be a positive integer.")

    task_root = _resolve_task_root(config)
    task_dir = task_root / f"pr-{pr_number}"
    _validate_task_path(config, task_root, task_dir)

    with connect(sqlite_path) as connection:
        pull_request = get_pull_request_inspection(connection, pr_number=pr_number)

    if pull_request is None:
        raise TaskBundleError(f"No saved PR found for #{pr_number}.")
    if not pull_request.merged_commit_sha:
        raise TaskBundleError(f"Saved PR #{pr_number} has no merged commit SHA.")

    worktree_path = prepare_oss_015_worktree(config, pr_number=pr_number)
    diff_text = _get_pr_diff(config, pull_request.merged_commit_sha)

    if task_dir.exists():
        _validate_task_path(config, task_root, task_dir)
        shutil.rmtree(task_dir)

    output_dir = task_dir / "output"
    logs_dir = output_dir / "logs"
    patches_dir = output_dir / "patches"
    logs_dir.mkdir(parents=True, exist_ok=True)
    patches_dir.mkdir(parents=True, exist_ok=True)

    pr_json_path = task_dir / "pr.json"
    files_changed_json_path = task_dir / "files_changed.json"
    diff_path = task_dir / "pr.diff"
    instructions_path = task_dir / "instructions.md"

    _write_json(pr_json_path, _pr_payload(pull_request))
    _write_json(files_changed_json_path, _files_payload(pull_request))
    diff_path.write_text(diff_text, encoding="utf-8")
    instructions_path.write_text(
        _instructions_for(config, pull_request, worktree_path),
        encoding="utf-8",
    )

    return TaskBundle(
        pr_number=pr_number,
        task_dir=task_dir,
        worktree_path=worktree_path,
        pr_json_path=pr_json_path,
        files_changed_json_path=files_changed_json_path,
        diff_path=diff_path,
        instructions_path=instructions_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        patches_dir=patches_dir,
    )


def _resolve_task_root(config: HarnessConfig) -> Path:
    if config.security.task_dir is not None:
        return config.security.task_dir

    return config.storage.sqlite_path.parent / "tasks"


def _validate_task_path(config: HarnessConfig, task_root: Path, task_dir: Path) -> None:
    validate_public_path(task_root, config.security.forbidden_private_prefixes)
    validate_public_path(task_dir, config.security.forbidden_private_prefixes)
    validate_safe_child_path(task_dir, task_root)
    validate_no_path_overlap(
        task_dir,
        config.local_repo.repo_dir,
        message="Refusing to use task path that overlaps upstream repo",
    )
    validate_no_path_overlap(
        task_dir,
        config.local_repo.worktree_dir,
        message="Refusing to use task path that overlaps worktree dir",
    )


def _get_pr_diff(config: HarnessConfig, merged_commit_sha: str) -> str:
    result = run_git(
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "show",
            "--format=",
            "--no-ext-diff",
            merged_commit_sha,
        ]
    )
    return result.stdout


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _pr_payload(pull_request: InspectedPullRequest) -> dict[str, object]:
    return {
        "github_pr_number": pull_request.github_pr_number,
        "github_pr_url": pull_request.github_pr_url,
        "title": pull_request.title,
        "body": pull_request.body,
        "source_branch": pull_request.source_branch,
        "target_branch": pull_request.target_branch,
        "merged_commit_sha": pull_request.merged_commit_sha,
        "created_at": pull_request.created_at,
        "updated_at": pull_request.updated_at,
        "closed_at": pull_request.closed_at,
        "merged_at": pull_request.merged_at,
        "author": pull_request.author,
    }


def _files_payload(pull_request: InspectedPullRequest) -> list[dict[str, object]]:
    return [
        {
            "filename": changed_file.filename,
            "status": changed_file.status,
            "additions": changed_file.additions,
            "deletions": changed_file.deletions,
            "is_test_file": changed_file.is_test_file,
            "is_docs_file": changed_file.is_docs_file,
            "is_ci_file": changed_file.is_ci_file,
        }
        for changed_file in pull_request.files
    ]


def _instructions_for(
    config: HarnessConfig,
    pull_request: InspectedPullRequest,
    worktree_path: Path,
) -> str:
    if pull_request.target_branch == "0.15":
        task = (
            "Classify whether this upstream 0.15 PR is a real bugfix candidate "
            "for human review."
        )
        allowed_decisions = (
            "DIRECT_015_BUGFIX, DISCARDED_NON_BUGFIX, DISCARDED_DOCS_ONLY, "
            "DISCARDED_CI_ONLY, DISCARDED_RELEASE_ONLY, NEEDS_HUMAN_REVIEW, "
            "INCONCLUSIVE, FAILED_INFRA"
        )
    else:
        task = (
            "Classify whether this master PR is a real bugfix and whether it is "
            "applicable to public OSS 0.15."
        )
        allowed_decisions = (
            "MASTER_NOT_APPLICABLE, MASTER_POSSIBLY_APPLICABLE, "
            "MASTER_REPRODUCED_ON_015, MASTER_FIX_VERIFIED_ON_015, INCONCLUSIVE, "
            "NEEDS_HUMAN_REVIEW, DISCARDED_NON_BUGFIX, DISCARDED_DOCS_ONLY, "
            "DISCARDED_CI_ONLY, DISCARDED_RELEASE_ONLY, FAILED_INFRA"
        )

    return f"""# Backport Analysis Task for PR #{pull_request.github_pr_number}

## Security Boundary

Use only public upstream data included in this task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, or private paths.

## Public Context

- PR metadata: `pr.json`
- Changed files: `files_changed.json`
- Public PR diff: `pr.diff`
- Public OSS 0.15 worktree: `{worktree_path}`

## Task

{task}

Allowed decisions: {allowed_decisions}

Write strict JSON output to `{config.codex.result_file}`.
If uncertain, choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`; do not silently discard uncertain cases.
"""
