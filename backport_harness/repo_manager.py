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
        run_git(["git", "clone", config.local_repo.upstream_url, str(repo_dir)])
    else:
        _verify_existing_repo_remote(repo_dir, config.local_repo.upstream_url)

    _fetch_configured_branches(repo_dir, config.github.branches)
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


def _fetch_configured_branches(repo_dir: Path, branches: list[str]) -> None:
    run_git(["git", "-C", str(repo_dir), "fetch", "origin", *branches, "--prune"])
