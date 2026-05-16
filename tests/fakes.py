from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backport_harness.codex_runner import CodexRunResult
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
from backport_harness.storage import connect
from backport_harness.task_builder import TaskBundle


class FakeGitHubClient:
    def __init__(
        self,
        pull_requests: dict[str, list[GitHubPullRequest]] | None = None,
        files: dict[int, list[GitHubChangedFile]] | None = None,
        fail_branch: str | None = None,
    ) -> None:
        self.pull_requests = pull_requests or {}
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


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int | None = 0,
        timeout: bool = False,
        stdout: str = '{"session":{"id":"12345678-1234-5678-1234-567812345678"}}\n',
        stderr: str = "stderr\n",
    ) -> None:
        self.pid = 123
        self.returncode = returncode
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode


def make_config(
    tmp_path: Path,
    *,
    sqlite_path: Path | None = None,
    forbidden_private_prefixes: list[Path] | None = None,
) -> HarnessConfig:
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
            repo_dir=tmp_path / "workspace" / "upstream",
            worktree_dir=tmp_path / "workspace" / "worktrees",
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
        storage=StorageConfig(
            sqlite_path=sqlite_path or tmp_path / "workspace" / "db.sqlite3"
        ),
        security=SecurityConfig(
            forbidden_private_prefixes=forbidden_private_prefixes or []
        ),
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


def insert_saved_pr(
    connection,
    *,
    number: int = 12345,
    status: str = "QUEUED_FOR_ANALYSIS",
    branch: str = "master",
    attempts: int = 0,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            target_branch,
            merged_commit_sha,
            merged_at,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            number,
            f"https://github.com/apache/hudi/pull/{number}",
            "Analyze me",
            branch,
            "abc123",
            "2024-01-01T00:00:00Z",
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
            status,
            20,
            attempts,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    return pr_id


def make_task_bundle(tmp_path: Path, *, pr_number: int = 12345) -> TaskBundle:
    task_dir = tmp_path / "workspace" / "tasks" / f"pr-{pr_number}"
    output_dir = task_dir / "output"
    logs_dir = output_dir / "logs"
    patches_dir = output_dir / "patches"
    instructions_path = task_dir / "instructions.md"
    logs_dir.mkdir(parents=True)
    patches_dir.mkdir(parents=True)
    instructions_path.write_text("analyze this\n", encoding="utf-8")
    return TaskBundle(
        pr_number=pr_number,
        task_dir=task_dir,
        worktree_path=tmp_path / "workspace" / "worktrees" / f"pr-{pr_number}-015",
        pr_json_path=task_dir / "pr.json",
        files_changed_json_path=task_dir / "files_changed.json",
        diff_path=task_dir / "pr.diff",
        instructions_path=instructions_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        patches_dir=patches_dir,
    )


def codex_run_result(
    task_dir: Path,
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
    stdout: str = "stdout\n",
    stderr: str = "stderr\n",
) -> CodexRunResult:
    stdout_log_path = task_dir / "output" / "logs" / "codex-stdout.log"
    stderr_log_path = task_dir / "output" / "logs" / "codex-stderr.log"
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_log_path.write_text(stdout, encoding="utf-8")
    stderr_log_path.write_text(stderr, encoding="utf-8")
    return CodexRunResult(
        session_id="00000000-0000-0000-0000-000000000000",
        exit_code=exit_code,
        timed_out=timed_out,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        last_message_path=None,
        started_at="2024-01-01T00:00:00Z",
        finished_at="2024-01-01T00:01:00Z",
    )


def write_valid_codex_result(task_dir: Path, *, pr_number: int = 12345) -> None:
    (task_dir / "output" / "logs" / "test-before-fix.log").write_text(
        "before\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "logs" / "test-after-fix.log").write_text(
        "after\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "patches" / "adapted-fix.patch").write_text(
        "patch\n",
        encoding="utf-8",
    )
    (task_dir / "output" / "codex_result.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pr_number": pr_number,
                "target_branch": "master",
                "decision": "MASTER_FIX_VERIFIED_ON_015",
                "confidence": "very_high",
                "summary": "Fixes null handling in compaction scheduling.",
                "human_action": "Review adapted patch and backport if appropriate.",
                "applicability": {
                    "applies_to_oss_015": True,
                    "reason": "The affected class and method exist in OSS 0.15.",
                    "affected_public_paths": [
                        "hudi-client/src/main/java/example/Foo.java",
                    ],
                    "missing_public_paths": [],
                },
                "test_transplant": {
                    "attempted": True,
                    "result": "applied_and_compiled",
                    "notes": "Adapted imports.",
                },
                "test_before_fix": {
                    "attempted": True,
                    "command": "mvn test",
                    "exit_code": 1,
                    "result": "failed_with_expected_error",
                    "log_path": "output/logs/test-before-fix.log",
                },
                "fix_verification": {
                    "attempted": True,
                    "command": "mvn test",
                    "exit_code": 0,
                    "result": "passed_after_adapted_fix",
                    "patch_path": "output/patches/adapted-fix.patch",
                    "log_path": "output/logs/test-after-fix.log",
                },
                "evidence": [
                    {
                        "type": "code_presence",
                        "description": "Class Foo exists in OSS 0.15.",
                    },
                    {
                        "type": "test_failure",
                        "description": "Test fails with the expected error before the fix.",
                        "log_path": "output/logs/test-before-fix.log",
                        "exit_code": 1,
                    },
                    {
                        "type": "test_pass",
                        "description": "Test passes after the adapted fix.",
                        "log_path": "output/logs/test-after-fix.log",
                        "patch_path": "output/patches/adapted-fix.patch",
                        "exit_code": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def queue_row(sqlite_path: Path, pr_id: int):
    with connect(sqlite_path) as connection:
        return connection.execute(
            """
            SELECT status, attempts, locked_at, locked_by, last_error
            FROM analysis_queue
            WHERE pr_id = ?
            """,
            (pr_id,),
        ).fetchone()
