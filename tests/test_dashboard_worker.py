import json

import pytest
import requests

from backport_harness.dashboard.codex import Adaptation, CodexError, Review, Snapshot, StaticCodex
from backport_harness.dashboard.git import git, resolve_commit
from backport_harness.dashboard.store import DashboardStore, set_job
from backport_harness.dashboard.worker import DashboardWorker
from test_dashboard_git import commit, repositories


PATCH = (
    "diff --git a/conflict.txt b/conflict.txt\n"
    "--- a/conflict.txt\n+++ b/conflict.txt\n"
    "@@ -1 +1 @@\n-private behavior\n+private behavior with the fix\n"
)


class FakeCodex:
    available = True

    def __init__(self):
        self.calls = []

    def run(self, snapshot, upstream_diff, prompt, *, adapt, canceled):
        self.calls.append((snapshot.sha, prompt, adapt))
        assert snapshot.read("conflict.txt", 1)["text"]
        assert "diff --git" in upstream_diff
        if adapt:
            return Adaptation(patch=PATCH, notes="Preserve the fork behavior.")
        return Review(
            relevance="affected", severity="medium", notes="The old behavior is present.",
            evidence=[{"path": "conflict.txt", "line": 1}],
        )


@pytest.fixture
def service(tmp_path, repositories):
    upstream, fork, workspace, settings, _ = repositories
    commit(upstream, "clean.txt", "a clean fix\n", "Fix clean candidate")
    commit(upstream, "conflict.txt", "upstream fix\n", "Fix conflicting candidate")
    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    store.save_profile(settings)
    worker = DashboardWorker(store, workspace, FakeCodex())
    store.schedule(now=100)
    assert worker.run_next("scan")
    assert worker.run_next("git")
    assert worker.run_next("git")
    return worker, fork, settings


def jobs(worker, ident):
    with worker.store.transaction() as db:
        return dict(db.execute("SELECT * FROM dashboard_jobs WHERE id = ?", (ident,)).fetchone())


def candidate(worker, applicability):
    with worker.store.transaction() as db:
        return dict(db.execute(
            "SELECT * FROM dashboard_commits WHERE applicability = ?", (applicability,)
        ).fetchone())


def test_clean_write_and_duplicate_request(service):
    worker, fork, settings = service
    clean = candidate(worker, "applicable")
    before = resolve_commit(fork, "refs/heads/target")
    job = worker.store.request_commit(clean["id"], "apply")
    assert worker.store.request_commit(clean["id"], "apply") == job
    assert worker.run_next("git")
    written = jobs(worker, job)
    assert written["status"] == "succeeded", written["error"]
    assert written["expected_sha"] == before
    assert resolve_commit(fork, "refs/heads/target") == written["prepared_sha"]
    assert worker.workspace.applied_marker(settings, written["token"]) == written["prepared_sha"]
    assert worker.store.request_commit(clean["id"], "apply") == job
    assert not (fork / "clean.txt").exists()


def test_adaptation_preview_confirmation_and_stale_target(service):
    worker, fork, _ = service
    conflicted = candidate(worker, "conflict")
    assert worker.run_next("codex")
    assert candidate(worker, "conflict")["severity"] == "medium"
    first = worker.store.request_commit(conflicted["id"], "adapt", "preserve local behavior")
    assert worker.run_next("codex")
    prepared = jobs(worker, first)
    assert prepared["status"] == "awaiting_confirmation", prepared["error"]
    assert "+private behavior with the fix" in prepared["diff"]
    assert resolve_commit(fork, "refs/heads/target") == prepared["expected_sha"]
    git(fork, "switch", "target")
    moved = commit(fork, "extra.txt", "new fork head\n", "Unrelated fork change")
    git(fork, "switch", "main")
    assert worker.store.confirm(first, prepared["prepared_sha"]) == first
    assert worker.run_next("git")
    assert jobs(worker, first)["status"] == "stale"
    assert resolve_commit(fork, "refs/heads/target") == moved

    second = worker.store.retry(first)
    assert worker.run_next("codex")
    updated = jobs(worker, second)
    assert updated["expected_sha"] == moved
    worker.store.confirm(second, updated["prepared_sha"])
    assert worker.run_next("git")
    assert jobs(worker, second)["status"] == "succeeded"
    assert resolve_commit(fork, "refs/heads/target") == updated["prepared_sha"]


def test_checked_out_branch_and_cancellation(service):
    worker, fork, _ = service
    clean = candidate(worker, "applicable")
    git(fork, "switch", "target")
    before = resolve_commit(fork, "HEAD")
    job = worker.store.request_commit(clean["id"], "apply")
    assert worker.run_next("git")
    assert "checked out" in jobs(worker, job)["error"]
    assert resolve_commit(fork, "HEAD") == before
    retried = worker.store.retry(job)
    worker.store.cancel(retried)
    assert not worker.run_next("git")
    assert jobs(worker, retried)["status"] == "canceled"


def test_recovers_write_recorded_in_git_before_sqlite(service):
    worker, fork, settings = service
    clean = candidate(worker, "applicable")
    job_id = worker.store.request_commit(clean["id"], "apply")
    job = worker.store.claim("git")
    before = worker.workspace.snapshot(job["profile_id"], settings)
    _, patch = worker.workspace.prepare_pick(job["profile_id"], before, clean, job["token"])
    with worker.store.transaction(write=True) as db:
        set_job(db, job_id, "committing", expected_sha=before, prepared_sha=patch.sha, diff=patch.diff)
    worker.workspace.promote(job["profile_id"], settings, job["token"], patch)
    worker.recover()
    assert jobs(worker, job_id)["status"] == "succeeded"
    assert candidate(worker, "applicable")["applied_sha"] == resolve_commit(fork, "refs/heads/target")


def test_static_provider_requires_valid_evidence_and_bounds_tools(monkeypatch, service):
    worker, _, settings = service
    profile = worker.store.active_profile()["id"]
    snapshot = Snapshot(worker.workspace.mirror(profile), worker.workspace.snapshot(profile, settings))
    responses = [
        [{"type": "function_call", "name": "read_file", "call_id": "call_1",
          "arguments": json.dumps({"path": "../config", "start_line": 1})}],
        [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({
            "relevance": "affected", "severity": "major", "notes": "bad evidence",
            "evidence": [{"path": "../config", "line": 1}],
        })}]}],
    ]
    sent = []

    class Response:
        status_code = 200

        def json(self):
            return {"status": "completed", "output": responses.pop(0)}

    def post(_session, url, **kwargs):
        assert url == "https://api.openai.com/v1/responses"
        sent.append(json.loads(json.dumps(kwargs["json"])))
        return Response()

    monkeypatch.setattr(requests.Session, "post", post)
    with pytest.raises(CodexError, match="outside the readable snapshot"):
        StaticCodex("test-credential").run(
            snapshot, "patch", "", adapt=False, canceled=lambda: False
        )
    assert sent[0]["store"] is False
    assert sent[0]["reasoning"] == {"effort": "high"}
    assert {tool["name"] for tool in sent[0]["tools"]} == {"list_paths", "read_file"}
    assert "not a regular tracked file" in sent[1]["input"][-1]["output"]

    def timeout(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(requests.Session, "post", timeout)
    with pytest.raises(CodexError, match="timed out"):
        StaticCodex("test-credential").run(
            snapshot, "patch", "", adapt=False, canceled=lambda: False
        )
