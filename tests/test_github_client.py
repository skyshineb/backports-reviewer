from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backport_harness.config import GithubConfig
from backport_harness.github_client import GitHubClient, GitHubHTTPError


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: dict[str, str] | None = None,
        links: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.links = links or {}

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise GitHubHTTPError(f"status {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "params": params})
        return self.responses.pop(0)


def make_config(**overrides: Any) -> GithubConfig:
    values = {
        "owner": "apache",
        "repo": "hudi",
        "branches": ["master", "0.15"],
        "token_env": "GITHUB_TOKEN",
        "token": "token-value",
        "request_delay_seconds": 0.0,
        "page_delay_seconds": 0.0,
        "max_retries": 2,
        "backoff_multiplier": 2.0,
        "respect_rate_limit": True,
    }
    values.update(overrides)
    return GithubConfig(**values)


def test_list_merged_pull_requests_builds_from_date_query() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"items": [{"number": 123}]}),
            FakeResponse(200, pull_payload(123)),
        ]
    )
    client = GitHubClient(make_config(), session=session)

    pull_requests = client.list_merged_pull_requests("master", "2024-01-01", None)

    query = session.calls[0]["params"]["q"]
    assert "repo:apache/hudi" in query
    assert "base:master" in query
    assert "merged:>=2024-01-01" in query
    assert pull_requests[0].number == 123


def test_list_merged_pull_requests_builds_date_range_query() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"items": []}),
        ]
    )
    client = GitHubClient(make_config(), session=session)

    client.list_merged_pull_requests("0.15", "2024-01-01", "2024-12-31")

    query = session.calls[0]["params"]["q"]
    assert "base:0.15" in query
    assert "merged:2024-01-01..2024-12-31" in query


def test_list_pull_request_files_paginates_and_delays_between_pages() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            FakeResponse(
                200,
                [{"filename": "src/main.py", "status": "modified"}],
                links={"next": {"url": "https://api.github.com/page/2"}},
            ),
            FakeResponse(
                200,
                [{"filename": "tests/test_main.py", "additions": 2, "deletions": 1}],
            ),
        ]
    )
    client = GitHubClient(
        make_config(page_delay_seconds=3.0),
        session=session,
        sleep=sleeps.append,
    )

    files = client.list_pull_request_files(123)

    assert [changed_file.filename for changed_file in files] == [
        "src/main.py",
        "tests/test_main.py",
    ]
    assert sleeps == [3.0]


def test_retryable_status_uses_exponential_backoff() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            FakeResponse(500, {}),
            FakeResponse(200, {"items": []}),
        ]
    )
    client = GitHubClient(
        make_config(backoff_multiplier=2.0),
        session=session,
        sleep=sleeps.append,
    )

    client.list_merged_pull_requests("master", "2024-01-01", None)

    assert sleeps == [1.0]
    assert len(session.calls) == 2


def test_rate_limit_reset_header_is_respected() -> None:
    sleeps: list[float] = []
    reset_at = int((datetime.now(timezone.utc) + timedelta(seconds=5)).timestamp())
    session = FakeSession(
        [
            FakeResponse(
                200,
                {"items": []},
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": str(reset_at),
                },
            )
        ]
    )
    client = GitHubClient(session=session, config=make_config(), sleep=sleeps.append)

    client.list_merged_pull_requests("master", "2024-01-01", None)

    assert sleeps
    assert 0 < sleeps[0] <= 5


def test_retry_failure_raises_after_max_attempts() -> None:
    session = FakeSession(
        [
            FakeResponse(429, {}),
            FakeResponse(429, {}),
        ]
    )
    client = GitHubClient(make_config(max_retries=1), session=session)

    with pytest.raises(GitHubHTTPError):
        client.list_merged_pull_requests("master", "2024-01-01", None)


def pull_payload(number: int) -> dict[str, Any]:
    return {
        "number": number,
        "html_url": f"https://github.com/apache/hudi/pull/{number}",
        "title": "Fix issue",
        "body": "Body",
        "head": {"ref": "feature"},
        "base": {"ref": "master"},
        "merge_commit_sha": "abc123",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "closed_at": "2024-01-03T00:00:00Z",
        "merged_at": "2024-01-03T00:00:00Z",
        "user": {"login": "octocat"},
    }
