from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from typing import Any, Callable
from urllib.error import HTTPError as UrlLibHTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import requests
except ModuleNotFoundError:
    requests = None

from backport_harness.config import GithubConfig


GITHUB_API_URL = "https://api.github.com"
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}


class GitHubHTTPError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubChangedFile:
    filename: str
    status: str | None
    additions: int | None
    deletions: int | None


@dataclass(frozen=True)
class GitHubPullRequest:
    number: int
    html_url: str
    title: str
    body: str | None
    head_ref: str | None
    base_ref: str
    merge_commit_sha: str | None
    created_at: str | None
    updated_at: str | None
    closed_at: str | None
    merged_at: str
    author: str | None


class GitHubClient:
    def __init__(
        self,
        config: GithubConfig,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._session = session or _default_session()
        self._sleep = sleep

    def list_merged_pull_requests(
        self,
        branch: str,
        from_date: str,
        to_date: str | None,
    ) -> list[GitHubPullRequest]:
        query = self._build_search_query(branch, from_date, to_date)
        pull_requests: list[GitHubPullRequest] = []

        for item in self._paginate(
            "/search/issues",
            params={"q": query, "sort": "updated", "order": "asc", "per_page": 100},
            item_key="items",
        ):
            number = item["number"]
            pull_requests.append(self.get_pull_request(number))

        return pull_requests

    def get_pull_request(self, number: int) -> GitHubPullRequest:
        data = self._get_json(f"/repos/{self._repo_path}/pulls/{number}")
        return GitHubPullRequest(
            number=int(data["number"]),
            html_url=data["html_url"],
            title=data["title"],
            body=data.get("body"),
            head_ref=_nested_get(data, "head", "ref"),
            base_ref=_nested_get(data, "base", "ref") or "",
            merge_commit_sha=data.get("merge_commit_sha"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            closed_at=data.get("closed_at"),
            merged_at=data["merged_at"],
            author=_nested_get(data, "user", "login"),
        )

    def list_pull_request_files(self, number: int) -> list[GitHubChangedFile]:
        files: list[GitHubChangedFile] = []
        for item in self._paginate(f"/repos/{self._repo_path}/pulls/{number}/files"):
            files.append(
                GitHubChangedFile(
                    filename=item["filename"],
                    status=item.get("status"),
                    additions=item.get("additions"),
                    deletions=item.get("deletions"),
                )
            )
        return files

    def _build_search_query(
        self,
        branch: str,
        from_date: str,
        to_date: str | None,
    ) -> str:
        date_range = f">={from_date}" if to_date is None else f"{from_date}..{to_date}"
        return (
            f"repo:{self._repo_path} "
            f"is:pr is:merged "
            f"base:{branch} "
            f"merged:{date_range}"
        )

    def _paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        item_key: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = f"{GITHUB_API_URL}{path}"
        current_params = params

        while next_url:
            response = self._request(next_url, current_params)
            data = response.json()
            page_items = data[item_key] if item_key else data
            items.extend(page_items)
            next_url = response.links.get("next", {}).get("url")
            current_params = None
            if next_url and self._config.page_delay_seconds > 0:
                self._sleep(self._config.page_delay_seconds)

        return items

    def _get_json(self, path: str) -> dict[str, Any]:
        response = self._request(f"{GITHUB_API_URL}{path}", None)
        return response.json()

    def _request(
        self,
        url: str,
        params: dict[str, Any] | None,
    ) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "backports-reviewer",
        }
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"

        attempt = 0
        while True:
            response = self._session.get(url, headers=headers, params=params)
            self._respect_rate_limit(response)

            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                self._delay_after_request()
                return response

            if attempt >= self._config.max_retries:
                response.raise_for_status()

            self._sleep(self._config.backoff_multiplier**attempt)
            attempt += 1

    def _respect_rate_limit(self, response: Any) -> None:
        if not self._config.respect_rate_limit:
            return
        if response.headers.get("x-ratelimit-remaining") != "0":
            return

        reset_header = response.headers.get("x-ratelimit-reset")
        if reset_header is None:
            return

        reset_at = datetime.fromtimestamp(int(reset_header), tz=timezone.utc)
        delay = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if delay > 0:
            self._sleep(delay)

    def _delay_after_request(self) -> None:
        if self._config.request_delay_seconds > 0:
            self._sleep(self._config.request_delay_seconds)

    @property
    def _repo_path(self) -> str:
        return f"{self._config.owner}/{self._config.repo}"


def _nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _default_session() -> Any:
    if requests is not None:
        return requests.Session()
    return _UrlLibSession()


class _UrlLibSession:
    def get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> "_UrlLibResponse":
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request) as response:
                body = response.read().decode("utf-8")
                return _UrlLibResponse(
                    status_code=response.status,
                    payload=json.loads(body),
                    headers=response.headers,
                )
        except UrlLibHTTPError as error:
            body = error.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return _UrlLibResponse(
                status_code=error.code,
                payload=payload,
                headers=error.headers,
            )


class _UrlLibResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: Message,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {key.lower(): value for key, value in headers.items()}
        self.links = _parse_link_header(headers.get("Link"))

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise GitHubHTTPError(f"GitHub API returned HTTP {self.status_code}")


def _parse_link_header(value: str | None) -> dict[str, dict[str, str]]:
    if not value:
        return {}

    links: dict[str, dict[str, str]] = {}
    for segment in value.split(","):
        url_part, _, rel_part = segment.strip().partition(";")
        rel = rel_part.strip().removeprefix('rel="').removesuffix('"')
        if rel and url_part.startswith("<") and url_part.endswith(">"):
            links[rel] = {"url": url_part[1:-1]}
    return links
