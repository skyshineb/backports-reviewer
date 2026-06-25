from __future__ import annotations

from pathlib import Path

from backport_harness.config import HarnessConfig
from backport_harness.git_runner import run_git
from backport_harness.security import SecurityError, validate_public_path


class RepositoryError(RuntimeError):
    pass


def ensure_upstream_repo(config: HarnessConfig) -> Path:
    repo_dir = config.local_repo.repo_dir
    validate_public_path(repo_dir, config.security.forbidden_private_prefixes)
    validate_public_path(config.local_repo.worktree_dir, config.security.forbidden_private_prefixes)

    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        run_git(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                config.local_repo.upstream_url,
                str(repo_dir),
            ]
        )
    else:
        _verify_existing_repo_remote(repo_dir, config.local_repo.upstream_url)

    _fetch_configured_refs(
        repo_dir,
        branches=config.github.branches,
        branch_ref_map=config.github.branch_ref_map,
        target_ref=config.local_repo.target_ref.ref,
    )
    return repo_dir


def _verify_existing_repo_remote(repo_dir: Path, expected_url: str) -> None:
    if not repo_dir.is_dir():
        raise RepositoryError(f"Configured repo path exists but is not a directory: {repo_dir}")

    result = run_git(["git", "-C", str(repo_dir), "remote", "get-url", "origin"])
    actual_url = result.stdout.strip()
    if actual_url != expected_url:
        raise SecurityError(
            "Existing upstream repository remote does not match configured public URL: "
            f"{actual_url or '-'} != {expected_url}"
        )


def _fetch_configured_refs(
    repo_dir: Path,
    *,
    branches: list[str],
    branch_ref_map: dict[str, str],
    target_ref: str,
) -> None:
    remote_branches = [_remote_branch_name(branch, branch_ref_map) for branch in branches]
    upstream_branch = _target_remote_branch_name(target_ref)
    if upstream_branch is not None and upstream_branch not in remote_branches:
        remote_branches.append(upstream_branch)

    run_git(
        [
            "git",
            "-C",
            str(repo_dir),
            "fetch",
            "--filter=blob:none",
            "origin",
            *remote_branches,
            "--prune",
        ]
    )

    target_tag_refspec = _target_tag_refspec(target_ref)
    if target_tag_refspec is not None:
        run_git(
            [
                "git",
                "-C",
                str(repo_dir),
                "fetch",
                "--filter=blob:none",
                "origin",
                target_tag_refspec,
                "--prune",
            ]
        )


def _remote_branch_name(branch: str, branch_ref_map: dict[str, str]) -> str:
    return branch_ref_map.get(branch, branch)


def _target_remote_branch_name(target_ref: str) -> str | None:
    if target_ref.startswith("origin/"):
        return target_ref.removeprefix("origin/")
    if target_ref.startswith("refs/heads/"):
        return target_ref.removeprefix("refs/heads/")
    if target_ref.startswith("refs/tags/"):
        return None
    return target_ref


def _target_tag_refspec(target_ref: str) -> str | None:
    if not target_ref.startswith("refs/tags/"):
        return None
    return f"{target_ref}:{target_ref}"
