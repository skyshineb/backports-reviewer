from __future__ import annotations

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
)
from backport_harness.github_client import GitHubChangedFile, GitHubPullRequest
from backport_harness.scanner import scan_pull_requests
from backport_harness.storage import connect


class FakeGitHubClient:
    def __init__(
        self,
        pull_requests: dict[str, list[GitHubPullRequest]],
        files: dict[int, list[GitHubChangedFile]] | None = None,
        fail_branch: str | None = None,
    ) -> None:
        self.pull_requests = pull_requests
        self.files = files or {}
        self.fail_branch = fail_branch
        self.scanned_branches: list[str] = []

    def list_merged_pull_requests(
        self,
        branch: str,
        from_date: str,
        to_date: str | None,
    ) -> list[GitHubPullRequest]:
        self.scanned_branches.append(branch)
        if branch == self.fail_branch:
            raise RuntimeError("GitHub unavailable")
        return self.pull_requests.get(branch, [])

    def list_pull_request_files(self, number: int) -> list[GitHubChangedFile]:
        return self.files.get(number, [])


def test_scan_one_branch_saves_pr_files_queue_and_scan_run(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "workspace" / "db.sqlite3"
    config = make_config(tmp_path, sqlite_path)
    client = FakeGitHubClient(
        {"master": [pull_request(101, "master")]},
        {
            101: [
                changed_file("src/main.py"),
                changed_file("tests/test_main.py"),
                changed_file("docs/usage.md"),
                changed_file(".github/workflows/ci.yml"),
            ]
        },
    )

    summary = scan_pull_requests(
        config=config,
        sqlite_path=sqlite_path,
        from_date="2024-01-01",
        to_date="2024-12-31",
        branch="master",
        client=client,
    )

    with connect(sqlite_path) as connection:
        prs = connection.execute(
            "SELECT github_pr_number, target_branch, title FROM prs"
        ).fetchall()
        files = connection.execute(
            """
            SELECT filename, is_test_file, is_docs_file, is_ci_file
            FROM pr_files
            ORDER BY filename
            """
        ).fetchall()
        queue = connection.execute(
            "SELECT status, priority, attempts FROM analysis_queue"
        ).fetchall()
        scan_runs = connection.execute(
            "SELECT branch, status, prs_seen, prs_saved, last_error FROM scan_runs"
        ).fetchall()

    assert summary.prs_seen == 1
    assert summary.prs_saved == 1
    assert prs == [(101, "master", "Fix 101")]
    assert queue == [("QUEUED_FOR_ANALYSIS", 20, 0)]
    assert scan_runs == [("master", "SUCCESS", 1, 1, None)]
    assert (".github/workflows/ci.yml", 0, 0, 1) in files
    assert ("docs/usage.md", 0, 1, 0) in files
    assert ("tests/test_main.py", 1, 0, 0) in files


def test_scan_without_branch_scans_all_configured_branches(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "db.sqlite3"
    config = make_config(tmp_path, sqlite_path)
    client = FakeGitHubClient(
        {
            "master": [pull_request(101, "master")],
            "0.15": [pull_request(102, "0.15")],
        }
    )

    summary = scan_pull_requests(
        config=config,
        sqlite_path=sqlite_path,
        from_date="2024-01-01",
        client=client,
    )

    assert client.scanned_branches == ["master", "0.15"]
    assert summary.prs_seen == 2
    with connect(sqlite_path) as connection:
        branches = connection.execute(
            "SELECT branch FROM scan_runs ORDER BY id"
        ).fetchall()
    assert branches == [("master",), ("0.15",)]


def test_scan_rejects_unconfigured_branch(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "db.sqlite3"
    config = make_config(tmp_path, sqlite_path)

    with pytest.raises(ValueError, match="not configured"):
        scan_pull_requests(
            config=config,
            sqlite_path=sqlite_path,
            from_date="2024-01-01",
            branch="unknown",
            client=FakeGitHubClient({}),
        )


def test_rescan_updates_pr_and_files_without_overwriting_queue_state(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "db.sqlite3"
    config = make_config(tmp_path, sqlite_path)

    scan_pull_requests(
        config=config,
        sqlite_path=sqlite_path,
        from_date="2024-01-01",
        branch="master",
        client=FakeGitHubClient(
            {"master": [pull_request(101, "master", title="Original")]},
            {101: [changed_file("src/old.py")]},
        ),
    )
    with connect(sqlite_path) as connection:
        connection.execute(
            """
            UPDATE analysis_queue
            SET status = 'IN_PROGRESS',
                priority = 5,
                attempts = 2,
                last_error = 'keep me'
            """
        )

    scan_pull_requests(
        config=config,
        sqlite_path=sqlite_path,
        from_date="2024-01-01",
        branch="master",
        client=FakeGitHubClient(
            {"master": [pull_request(101, "master", title="Updated")]},
            {101: [changed_file("src/new.py")]},
        ),
    )

    with connect(sqlite_path) as connection:
        prs = connection.execute("SELECT title FROM prs").fetchall()
        files = connection.execute("SELECT filename FROM pr_files").fetchall()
        queue = connection.execute(
            "SELECT status, priority, attempts, last_error FROM analysis_queue"
        ).fetchall()

    assert prs == [("Updated",)]
    assert files == [("src/new.py",)]
    assert queue == [("IN_PROGRESS", 5, 2, "keep me")]


def test_failed_scan_records_audit_row(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "db.sqlite3"
    config = make_config(tmp_path, sqlite_path)

    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        scan_pull_requests(
            config=config,
            sqlite_path=sqlite_path,
            from_date="2024-01-01",
            branch="master",
            client=FakeGitHubClient({}, fail_branch="master"),
        )

    with connect(sqlite_path) as connection:
        scan_runs = connection.execute(
            "SELECT status, prs_seen, prs_saved, last_error FROM scan_runs"
        ).fetchall()

    assert scan_runs == [("FAILED", 0, 0, "GitHub unavailable")]


def make_config(tmp_path: Path, sqlite_path: Path) -> HarnessConfig:
    return HarnessConfig(
        github=GithubConfig(
            owner="apache",
            repo="hudi",
            branches=["master", "0.15"],
            token_env="GITHUB_TOKEN",
            token=None,
        ),
        local_repo=LocalRepoConfig(
            upstream_url="https://github.com/apache/hudi.git",
            repo_dir=tmp_path / "upstream",
            worktree_dir=tmp_path / "worktrees",
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
        storage=StorageConfig(sqlite_path=sqlite_path),
        security=SecurityConfig(forbidden_private_prefixes=[]),
    )


def pull_request(
    number: int,
    branch: str,
    title: str | None = None,
) -> GitHubPullRequest:
    return GitHubPullRequest(
        number=number,
        html_url=f"https://github.com/apache/hudi/pull/{number}",
        title=title or f"Fix {number}",
        body=None,
        head_ref="feature",
        base_ref=branch,
        merge_commit_sha="abc123",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
        closed_at="2024-01-03T00:00:00Z",
        merged_at="2024-01-03T00:00:00Z",
        author="octocat",
    )


def changed_file(filename: str) -> GitHubChangedFile:
    return GitHubChangedFile(
        filename=filename,
        status="modified",
        additions=1,
        deletions=1,
    )
