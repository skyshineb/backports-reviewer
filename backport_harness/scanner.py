from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backport_harness.config import HarnessConfig
from backport_harness.github_client import GitHubClient
from backport_harness.storage import (
    connect,
    create_analysis_queue_row_if_missing,
    create_scan_run,
    finish_scan_run,
    init_database,
    replace_pull_request_files,
    upsert_pull_request,
)


@dataclass(frozen=True)
class BranchScanSummary:
    branch: str
    prs_seen: int
    prs_saved: int
    status: str


@dataclass(frozen=True)
class ScanSummary:
    branches: list[BranchScanSummary]

    @property
    def prs_seen(self) -> int:
        return sum(branch.prs_seen for branch in self.branches)

    @property
    def prs_saved(self) -> int:
        return sum(branch.prs_saved for branch in self.branches)


def scan_pull_requests(
    config: HarnessConfig,
    sqlite_path: Path,
    from_date: str,
    to_date: str | None = None,
    branch: str | None = None,
    client: GitHubClient | None = None,
) -> ScanSummary:
    branches = _selected_branches(config, branch)
    github_client = client or GitHubClient(config.github)
    init_database(sqlite_path)

    summaries: list[BranchScanSummary] = []
    for selected_branch in branches:
        summaries.append(
            _scan_branch(
                config=config,
                sqlite_path=sqlite_path,
                client=github_client,
                branch=selected_branch,
                from_date=from_date,
                to_date=to_date,
            )
        )

    return ScanSummary(branches=summaries)


def _scan_branch(
    config: HarnessConfig,
    sqlite_path: Path,
    client: GitHubClient,
    branch: str,
    from_date: str,
    to_date: str | None,
) -> BranchScanSummary:
    prs_seen = 0
    prs_saved = 0

    with connect(sqlite_path) as connection:
        scan_run_id = create_scan_run(connection, branch, from_date, to_date)

    try:
        pull_requests = client.list_merged_pull_requests(branch, from_date, to_date)
        prs_seen = len(pull_requests)

        for pull_request in pull_requests:
            files = client.list_pull_request_files(pull_request.number)
            with connect(sqlite_path) as connection:
                pr_id = upsert_pull_request(connection, pull_request)
                replace_pull_request_files(connection, pr_id, files)
                create_analysis_queue_row_if_missing(connection, pr_id)
            prs_saved += 1

        with connect(sqlite_path) as connection:
            finish_scan_run(
                connection,
                scan_run_id,
                "SUCCESS",
                prs_seen=prs_seen,
                prs_saved=prs_saved,
            )
        return BranchScanSummary(
            branch=branch,
            prs_seen=prs_seen,
            prs_saved=prs_saved,
            status="SUCCESS",
        )
    except Exception as error:
        with connect(sqlite_path) as connection:
            finish_scan_run(
                connection,
                scan_run_id,
                "FAILED",
                prs_seen=prs_seen,
                prs_saved=prs_saved,
                last_error=str(error),
            )
        raise


def _selected_branches(config: HarnessConfig, branch: str | None) -> list[str]:
    if branch is None:
        return config.github.branches
    if branch not in config.github.branches:
        raise ValueError(
            f"Branch {branch!r} is not configured. "
            f"Configured branches: {', '.join(config.github.branches)}"
        )
    return [branch]
