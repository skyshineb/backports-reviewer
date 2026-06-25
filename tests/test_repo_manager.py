from dataclasses import replace
from pathlib import Path

import pytest

from backport_harness.config import (
    AnalysisConfig,
    CodexConfig,
    GithubConfig,
    HarnessConfig,
    LocalRepoConfig,
    ReportsConfig,
    SecurityConfig,
    StorageConfig,
    TargetRefConfig,
)
from backport_harness.git_runner import GitResult
from backport_harness.repo_manager import ensure_upstream_repo
from backport_harness.security import SecurityError


def test_ensure_upstream_repo_clones_when_repo_missing(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    calls = []

    def fake_run_git(args):
        calls.append(args)
        return GitResult(args=args, stdout="", stderr="")

    monkeypatch.setattr("backport_harness.repo_manager.run_git", fake_run_git)

    ensure_upstream_repo(config)

    assert calls == [
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            config.local_repo.upstream_url,
            str(config.local_repo.repo_dir),
        ],
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "fetch",
            "--filter=blob:none",
            "origin",
            "master",
            "release-0.15.0",
            "--prune",
        ],
    ]


def test_ensure_upstream_repo_checks_remote_and_fetches_existing_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    config.local_repo.repo_dir.mkdir(parents=True)
    calls = []

    def fake_run_git(args):
        calls.append(args)
        stdout = config.local_repo.upstream_url + "\n" if "remote" in args else ""
        return GitResult(args=args, stdout=stdout, stderr="")

    monkeypatch.setattr("backport_harness.repo_manager.run_git", fake_run_git)

    ensure_upstream_repo(config)

    assert calls == [
        ["git", "-C", str(config.local_repo.repo_dir), "remote", "get-url", "origin"],
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "fetch",
            "--filter=blob:none",
            "origin",
            "master",
            "release-0.15.0",
            "--prune",
        ],
    ]


def test_ensure_upstream_repo_fetches_configured_tag_target_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    config = replace(
        config,
        github=replace(config.github, branches=["main"]),
        local_repo=replace(
            config.local_repo,
            upstream_url="https://github.com/lance-format/lance.git",
            target_ref=TargetRefConfig(
                label="v7.0.0",
                ref="refs/tags/v7.0.0",
                worktree_suffix="v7.0.0",
            ),
        ),
    )
    calls = []

    def fake_run_git(args):
        calls.append(args)
        return GitResult(args=args, stdout="", stderr="")

    monkeypatch.setattr("backport_harness.repo_manager.run_git", fake_run_git)

    ensure_upstream_repo(config)

    assert calls == [
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            config.local_repo.upstream_url,
            str(config.local_repo.repo_dir),
        ],
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "fetch",
            "--filter=blob:none",
            "origin",
            "main",
            "--prune",
        ],
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "fetch",
            "--filter=blob:none",
            "origin",
            "refs/tags/v7.0.0:refs/tags/v7.0.0",
            "--prune",
        ],
    ]


def test_ensure_upstream_repo_rejects_remote_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    config.local_repo.repo_dir.mkdir(parents=True)

    def fake_run_git(args):
        return GitResult(args=args, stdout="https://example.com/private.git\n", stderr="")

    monkeypatch.setattr("backport_harness.repo_manager.run_git", fake_run_git)

    with pytest.raises(SecurityError, match="remote does not match"):
        ensure_upstream_repo(config)


def test_ensure_upstream_repo_rejects_forbidden_paths(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        forbidden_private_prefixes=[tmp_path / "workspace"],
    )

    with pytest.raises(SecurityError, match="forbidden private prefix"):
        ensure_upstream_repo(config)


def make_config(
    tmp_path: Path,
    *,
    forbidden_private_prefixes: list[Path] | None = None,
) -> HarnessConfig:
    return HarnessConfig(
        github=GithubConfig(
            owner="apache",
            repo="hudi",
            branches=["master", "0.15"],
            token_env="GITHUB_TOKEN",
            token=None,
            branch_ref_map={"0.15": "release-0.15.0"},
        ),
        local_repo=LocalRepoConfig(
            upstream_url="https://github.com/apache/hudi.git",
            repo_dir=tmp_path / "workspace" / "upstream",
            worktree_dir=tmp_path / "workspace" / "worktrees",
            target_ref=TargetRefConfig(
                label="0.15",
                ref="origin/release-0.15.0",
                worktree_suffix="015",
            ),
        ),
        codex=CodexConfig(
            command="codex",
            mode="exec",
            timeout_seconds=7200,
            max_attempts_per_pr=2,
            result_file="output/codex_result.json",
        ),
        analysis=AnalysisConfig(default_limit=5, stale_timeout_seconds=7200),
        reports=ReportsConfig(output_dir=tmp_path / "reports"),
        storage=StorageConfig(sqlite_path=tmp_path / "workspace" / "db.sqlite3"),
        security=SecurityConfig(
            forbidden_private_prefixes=forbidden_private_prefixes or []
        ),
    )
