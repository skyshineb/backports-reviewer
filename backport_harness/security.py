from __future__ import annotations

from pathlib import Path


class SecurityError(ValueError):
    pass


def validate_public_path(path: Path, forbidden_prefixes: list[Path]) -> None:
    resolved_path = _resolve_for_validation(path)
    for forbidden_prefix in forbidden_prefixes:
        resolved_prefix = _resolve_for_validation(forbidden_prefix)
        if _paths_overlap(resolved_path, resolved_prefix):
            raise SecurityError(
                "Configured path overlaps forbidden private prefix: "
                f"{resolved_path} overlaps {resolved_prefix}"
            )


def validate_safe_child_path(child: Path, parent: Path) -> None:
    resolved_child = _resolve_for_validation(child)
    resolved_parent = _resolve_for_validation(parent)
    if resolved_child == resolved_parent or resolved_parent not in resolved_child.parents:
        raise SecurityError(f"Path {resolved_child} is not inside {resolved_parent}.")


def validate_safe_stale_worktree_removal(
    *,
    target: Path,
    worktree_dir: Path,
    repo_dir: Path,
    forbidden_prefixes: list[Path],
) -> None:
    validate_public_path(target, forbidden_prefixes)
    validate_safe_child_path(target, worktree_dir)

    resolved_target = _resolve_for_validation(target)
    resolved_repo = _resolve_for_validation(repo_dir)
    if _paths_overlap(resolved_target, resolved_repo):
        raise SecurityError(
            f"Refusing to remove worktree path {resolved_target}; it overlaps repo {resolved_repo}."
        )


def validate_no_path_overlap(first: Path, second: Path, *, message: str) -> None:
    resolved_first = _resolve_for_validation(first)
    resolved_second = _resolve_for_validation(second)
    if _paths_overlap(resolved_first, resolved_second):
        raise SecurityError(f"{message}: {resolved_first} overlaps {resolved_second}.")


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _resolve_for_validation(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
