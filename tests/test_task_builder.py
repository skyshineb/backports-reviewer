import json
from pathlib import Path

import pytest

from backport_harness.config import SecurityConfig
from backport_harness.git_runner import GitResult
from backport_harness.security import SecurityError
from backport_harness.storage import connect, init_database
from backport_harness.task_builder import TaskBundleError, build_task_bundle
from tests.test_repo_manager import make_config


def test_build_task_bundle_writes_expected_files_and_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, branch="master")
    calls = []

    monkeypatch.setattr(
        "backport_harness.task_builder.prepare_oss_015_worktree",
        lambda config, pr_number: config.local_repo.worktree_dir / "pr-12345-015",
    )

    def fake_run_git(args):
        calls.append(args)
        return GitResult(args=args, stdout="diff --git a/file b/file\n", stderr="")

    monkeypatch.setattr("backport_harness.task_builder.run_git", fake_run_git)

    bundle = build_task_bundle(
        config=config,
        sqlite_path=sqlite_path,
        pr_number=12345,
    )

    assert bundle.task_dir == tmp_path / "workspace" / "tasks" / "pr-12345"
    assert bundle.pr_json_path.is_file()
    assert bundle.files_changed_json_path.is_file()
    assert bundle.diff_path.read_text(encoding="utf-8") == "diff --git a/file b/file\n"
    assert bundle.instructions_path.is_file()
    assert bundle.output_dir.is_dir()
    assert bundle.logs_dir.is_dir()
    assert bundle.patches_dir.is_dir()
    assert calls == [
        [
            "git",
            "-C",
            str(config.local_repo.repo_dir),
            "show",
            "--format=",
            "--no-ext-diff",
            "abc123",
        ]
    ]

    pr_payload = json.loads(bundle.pr_json_path.read_text(encoding="utf-8"))
    files_payload = json.loads(bundle.files_changed_json_path.read_text(encoding="utf-8"))
    assert pr_payload["github_pr_number"] == 12345
    assert pr_payload["target_branch"] == "master"
    assert files_payload == [
        {
            "additions": 10,
            "deletions": 2,
            "filename": "src/test/TestCompaction.java",
            "is_ci_file": False,
            "is_docs_file": False,
            "is_test_file": True,
            "status": "modified",
        }
    ]


def test_build_task_bundle_generates_branch_specific_instructions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, number=1, branch="master")
    _insert_saved_pr(sqlite_path, number=2, branch="0.15")
    monkeypatch.setattr(
        "backport_harness.task_builder.prepare_oss_015_worktree",
        lambda config, pr_number: config.local_repo.worktree_dir / f"pr-{pr_number}-015",
    )
    monkeypatch.setattr(
        "backport_harness.task_builder.run_git",
        lambda args: GitResult(args=args, stdout="diff\n", stderr=""),
    )

    master_bundle = build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=1)
    branch_bundle = build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=2)

    master_instructions = master_bundle.instructions_path.read_text(encoding="utf-8")
    branch_instructions = branch_bundle.instructions_path.read_text(encoding="utf-8")
    assert "Analyze Upstream Master PR" in master_instructions
    assert "applicable to public OSS 0.15" in master_instructions
    assert (
        f"Public OSS 0.15 worktree: `{config.local_repo.worktree_dir / 'pr-1-015'}`"
        in master_instructions
    )
    assert "worktree path supplied by the task builder" not in master_instructions
    assert "Analyze Upstream 0.15 PR" in branch_instructions
    assert "DIRECT_015_BUGFIX" in branch_instructions
    assert (
        f"Public OSS 0.15 worktree: `{config.local_repo.worktree_dir / 'pr-2-015'}`"
        in branch_instructions
    )
    assert "worktree path supplied by the task builder" not in branch_instructions
    assert "Do not use, request, infer, or reference private fork code" in master_instructions
    assert "output/codex_result.json" in branch_instructions
    assert "output/notes.md" in branch_instructions


def test_build_task_bundle_instructions_exclude_forbidden_private_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    private_path = tmp_path / "private"
    config = make_config(tmp_path, forbidden_private_prefixes=[private_path])
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, branch="master")
    monkeypatch.setattr(
        "backport_harness.task_builder.prepare_oss_015_worktree",
        lambda config, pr_number: config.local_repo.worktree_dir / "pr-12345-015",
    )
    monkeypatch.setattr(
        "backport_harness.task_builder.run_git",
        lambda args: GitResult(args=args, stdout="diff\n", stderr=""),
    )

    bundle = build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=12345)

    assert str(private_path) not in bundle.instructions_path.read_text(encoding="utf-8")


def test_build_task_bundle_replaces_existing_safe_task_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, branch="master")
    stale_file = tmp_path / "workspace" / "tasks" / "pr-12345" / "stale.txt"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(
        "backport_harness.task_builder.prepare_oss_015_worktree",
        lambda config, pr_number: config.local_repo.worktree_dir / "pr-12345-015",
    )
    monkeypatch.setattr(
        "backport_harness.task_builder.run_git",
        lambda args: GitResult(args=args, stdout="diff\n", stderr=""),
    )

    bundle = build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=12345)

    assert not stale_file.exists()
    assert bundle.instructions_path.exists()


def test_build_task_bundle_rejects_missing_pr(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    init_database(sqlite_path)

    with pytest.raises(TaskBundleError, match="No saved PR found"):
        build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=12345)


def test_build_task_bundle_rejects_missing_merge_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, branch="master", merged_commit_sha=None)
    monkeypatch.setattr(
        "backport_harness.task_builder.prepare_oss_015_worktree",
        lambda config, pr_number: config.local_repo.worktree_dir / "pr-12345-015",
    )

    with pytest.raises(TaskBundleError, match="merged commit SHA"):
        build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=12345)


def test_build_task_bundle_rejects_forbidden_task_path(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path)
    object.__setattr__(
        config,
        "security",
        SecurityConfig(
            forbidden_private_prefixes=[tmp_path / "private"],
            task_dir=tmp_path / "private" / "tasks",
        ),
    )
    init_database(sqlite_path)
    _insert_saved_pr(sqlite_path, branch="master")

    with pytest.raises(SecurityError, match="forbidden private prefix"):
        build_task_bundle(config=config, sqlite_path=sqlite_path, pr_number=12345)


def _insert_saved_pr(
    sqlite_path: Path,
    *,
    number: int = 12345,
    branch: str,
    merged_commit_sha: str | None = "abc123",
) -> None:
    with connect(sqlite_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO prs(
                github_pr_number,
                github_pr_url,
                title,
                body,
                source_branch,
                target_branch,
                merged_commit_sha,
                created_at,
                updated_at,
                closed_at,
                merged_at,
                author,
                created_in_db_at,
                updated_in_db_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                number,
                f"https://github.com/apache/hudi/pull/{number}",
                "Fix compaction bug",
                "Public body",
                "feature-branch",
                branch,
                merged_commit_sha,
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:02:00Z",
                "2024-01-01T00:03:00Z",
                "author",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
            ),
        )
        pr_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO analysis_queue(
                pr_id,
                status,
                priority,
                attempts,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pr_id,
                "QUEUED_FOR_ANALYSIS",
                100,
                0,
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO pr_files(
                pr_id,
                filename,
                status,
                additions,
                deletions,
                is_test_file,
                is_docs_file,
                is_ci_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pr_id,
                "src/test/TestCompaction.java",
                "modified",
                10,
                2,
                1,
                0,
                0,
            ),
        )
