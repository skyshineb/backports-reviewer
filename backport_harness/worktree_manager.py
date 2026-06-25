from __future__ import annotations

import shutil
from pathlib import Path

from backport_harness.config import HarnessConfig
from backport_harness.git_runner import GitCommandError, run_git
from backport_harness.repo_manager import ensure_upstream_repo
from backport_harness.security import (
    validate_no_path_overlap,
    validate_public_path,
    validate_safe_child_path,
    validate_safe_stale_worktree_removal,
)


def prepare_target_worktree(config: HarnessConfig, *, pr_number: int) -> Path:
    if pr_number < 1:
        raise ValueError("pr_number must be a positive integer.")

    validate_public_path(config.local_repo.repo_dir, config.security.forbidden_private_prefixes)
    validate_public_path(config.local_repo.worktree_dir, config.security.forbidden_private_prefixes)

    repo_dir = config.local_repo.repo_dir
    worktree_dir = config.local_repo.worktree_dir
    target_ref = config.local_repo.target_ref
    target = worktree_dir / f"pr-{pr_number}-{target_ref.worktree_suffix}"
    validate_public_path(target, config.security.forbidden_private_prefixes)
    validate_safe_child_path(target, worktree_dir)
    validate_no_path_overlap(
        target,
        repo_dir,
        message="Refusing to use worktree path that overlaps upstream repo",
    )
    repo_dir = ensure_upstream_repo(config)

    run_git(["git", "-C", str(repo_dir), "worktree", "prune"])

    if target.exists():
        validate_safe_stale_worktree_removal(
            target=target,
            worktree_dir=worktree_dir,
            repo_dir=repo_dir,
            forbidden_prefixes=config.security.forbidden_private_prefixes,
        )
        try:
            run_git(["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(target)])
        except GitCommandError:
            shutil.rmtree(target)

    worktree_dir.mkdir(parents=True, exist_ok=True)
    run_git(
        [
            "git",
            "-C",
            str(repo_dir),
            "worktree",
            "add",
            "--detach",
            str(target),
            target_ref.ref,
        ]
    )
    return target
