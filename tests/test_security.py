from __future__ import annotations

from pathlib import Path

import pytest

from backport_harness.codex_runner import CodexRunRequest, run_codex
from backport_harness.security import (
    SecurityError,
    validate_no_path_overlap,
    validate_public_path,
    validate_safe_child_path,
    validate_safe_stale_worktree_removal,
)
from tests.fakes import FakeProcess


def test_validate_public_path_rejects_path_inside_forbidden_prefix(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"

    with pytest.raises(SecurityError, match="forbidden private prefix"):
        validate_public_path(private_root / "checkout", [private_root])


def test_validate_public_path_rejects_parent_of_forbidden_prefix(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"

    with pytest.raises(SecurityError, match="forbidden private prefix"):
        validate_public_path(workspace, [workspace / "private-fork"])


def test_validate_safe_child_path_rejects_sibling_and_parent(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspace" / "worktrees"

    with pytest.raises(SecurityError, match="not inside"):
        validate_safe_child_path(tmp_path / "workspace" / "other", parent)

    with pytest.raises(SecurityError, match="not inside"):
        validate_safe_child_path(parent, parent)


def test_validate_stale_worktree_removal_rejects_repo_overlap(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "workspace" / "upstream"
    worktree_dir = repo_dir / "nested-worktrees"

    with pytest.raises(SecurityError, match="overlaps repo"):
        validate_safe_stale_worktree_removal(
            target=worktree_dir / "pr-12345-015",
            worktree_dir=worktree_dir,
            repo_dir=repo_dir,
            forbidden_prefixes=[],
        )


def test_validate_no_path_overlap_rejects_nested_paths(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="overlap"):
        validate_no_path_overlap(
            tmp_path / "workspace",
            tmp_path / "workspace" / "upstream",
            message="paths overlap",
        )


def test_run_codex_strips_github_credentials_but_preserves_normal_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "secret")
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")

    run_codex(
        CodexRunRequest(
            prompt="do work",
            cwd=tmp_path,
            timeout_seconds=30,
            output_result_path=tmp_path / "output" / "codex_result.json",
            extra_env={
                "CUSTOM_GITHUB_TOKEN": "custom-secret",
                "NORMAL_ENV": "keep-me",
            },
            github_token_env="CUSTOM_GITHUB_TOKEN",
        )
    )

    env = calls[0][1]["env"]
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "GITHUB_ENTERPRISE_TOKEN" not in env
    assert "GH_ENTERPRISE_TOKEN" not in env
    assert "CUSTOM_GITHUB_TOKEN" not in env
    assert env["OPENAI_API_KEY"] == "provider-secret"
    assert env["NORMAL_ENV"] == "keep-me"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
