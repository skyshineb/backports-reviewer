from pathlib import Path

import pytest

from backport_harness.git_runner import GitResult
from backport_harness.security import SecurityError
from backport_harness.worktree_manager import prepare_oss_015_worktree
from tests.test_repo_manager import make_config


def test_prepare_oss_015_worktree_creates_detached_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    calls = []

    monkeypatch.setattr(
        "backport_harness.worktree_manager.ensure_upstream_repo",
        lambda config: config.local_repo.repo_dir,
    )

    def fake_run_git(args):
        calls.append(args)
        return GitResult(args=args, stdout="", stderr="")

    monkeypatch.setattr("backport_harness.worktree_manager.run_git", fake_run_git)

    target = prepare_oss_015_worktree(config, pr_number=12345)

    assert target == config.local_repo.worktree_dir / "pr-12345-015"
    assert calls == [
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "worktree",
            "add",
            "--detach",
            str(target),
            "origin/0.15",
        ]
    ]


def test_prepare_oss_015_worktree_removes_safe_stale_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    target = config.local_repo.worktree_dir / "pr-12345-015"
    target.mkdir(parents=True)
    removed = []

    monkeypatch.setattr(
        "backport_harness.worktree_manager.ensure_upstream_repo",
        lambda config: config.local_repo.repo_dir,
    )
    monkeypatch.setattr(
        "backport_harness.worktree_manager.shutil.rmtree",
        lambda path: removed.append(path),
    )
    monkeypatch.setattr(
        "backport_harness.worktree_manager.run_git",
        lambda args: GitResult(args=args, stdout="", stderr=""),
    )

    prepare_oss_015_worktree(config, pr_number=12345)

    assert removed == [target]


def test_prepare_oss_015_worktree_rejects_forbidden_worktree_path(
    tmp_path: Path,
) -> None:
    config = make_config(
        tmp_path,
        forbidden_private_prefixes=[tmp_path / "workspace" / "worktrees"],
    )

    with pytest.raises(SecurityError, match="forbidden private prefix"):
        prepare_oss_015_worktree(config, pr_number=12345)


def test_prepare_oss_015_worktree_rejects_repo_overlap(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    overlapping_config = make_config(tmp_path)
    object.__setattr__(
        overlapping_config.local_repo,
        "worktree_dir",
        config.local_repo.repo_dir / "nested-worktrees",
    )

    with pytest.raises(SecurityError, match="overlaps upstream repo"):
        prepare_oss_015_worktree(overlapping_config, pr_number=12345)


def test_prepare_oss_015_worktree_rejects_invalid_pr_number(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="positive integer"):
        prepare_oss_015_worktree(config, pr_number=0)
