from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from backport_harness.dashboard.codex import StaticCodex
from backport_harness.dashboard.git import GitError, GitWorkspace, branch_ref, resolve_commit
from backport_harness.dashboard.models import ProfileSettings
from backport_harness.dashboard.store import ActionError, DashboardStore, current_job
from backport_harness.dashboard.worker import DashboardWorker

logger = logging.getLogger(__name__)
PAGE_SIZE = 30
MAX_FORM_BYTES = 32768
MAX_PROMPT = 6000
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".webp": "image/webp", ".woff2": "font/woff2",
}
JOB_SUMMARY = (
    "j.id, j.kind, j.commit_id, j.status, j.cancel_requested, j.automatic, "
    "j.expected_sha, j.prepared_sha, j.error, j.created_at, j.updated_at"
)


def recommendation(row: dict) -> str | None:
    if row["applicability"] == "empty":
        return "skip"
    if row["relevance"] == "affected":
        return "apply" if row["severity"] in {"major", "medium"} else "skip"
    if row["relevance"] in {"already_fixed", "not_affected"}:
        return "skip"
    if row["relevance"] == "unclear" or row["applicability"] == "applicable":
        return "review"
    return None


class DashboardHTTP(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, worker: DashboardWorker, token: str | None = None) -> None:
        self.worker = worker
        self.store = worker.store
        self.token = token or secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), DashboardHandler)
        self.host_header = f"127.0.0.1:{self.server_port}"
        self.origin = "http://" + self.host_header

    @property
    def launch_url(self) -> str:
        return f"{self.origin}/#{self.token}"

    def overview(self, query: dict) -> dict:
        profile = self.store.active_profile()
        data = {"profile": profile, "codex_available": self.worker.codex.available, "commits": []}
        if not profile:
            return data
        fork_head = None
        try:
            fork = self.worker.workspace.fork(Path(profile["fork_path"]))
            fork_head = resolve_commit(fork, branch_ref(profile["target_branch"]))
        except (GitError, OSError, ValueError) as error:
            data["fork_error"] = str(error)
        state = query.get("state", [""])[0]
        search = query.get("q", [""])[0].strip()[:240]
        page = page_number(query)
        filtered = (profile["id"], state, state, state, search, search, search)
        criteria = """
            profile_id = ? AND (? = '' OR applicability = ? OR decision = ?)
            AND (? = '' OR instr(lower(subject), lower(?)) > 0 OR instr(sha, ?) > 0)
        """
        with self.store.transaction() as db:
            rows = db.execute(
                f"""
                SELECT * FROM dashboard_commits WHERE {criteria}
                ORDER BY julianday(committed_at) DESC, id DESC LIMIT ? OFFSET ?
                """,
                (*filtered, PAGE_SIZE, page * PAGE_SIZE),
            )
            data["commits"] = [
                self.commit_summary(dict(row), fork_head) for row in rows
            ]
            data["total"] = db.execute(
                f"SELECT count(*) FROM dashboard_commits WHERE {criteria}", filtered
            ).fetchone()[0]
            data["last_scan"] = self.latest_scan(db, profile["id"])
            data["counts"] = dict(db.execute(
                """
                SELECT count(*) AS total,
                    count(CASE WHEN decision IS NULL THEN 1 END) AS review,
                    count(CASE WHEN decision = 'applied' THEN 1 END) AS applied
                FROM dashboard_commits WHERE profile_id = ?
                """,
                (profile["id"],),
            ).fetchone())
        data.update({"page": page, "page_size": PAGE_SIZE, "fork_head": fork_head})
        return data

    @staticmethod
    def latest_scan(db: sqlite3.Connection, profile: int) -> dict | None:
        row = db.execute(
            f"""
            SELECT {JOB_SUMMARY} FROM dashboard_jobs j
            WHERE j.profile_id = ? AND j.kind IN ('scan', 'rescan') ORDER BY j.id DESC LIMIT 1
            """,
            (profile,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def commit_summary(row: dict, fork_head: str | None) -> dict:
        row["recommendation"] = recommendation(row)
        row["stale"] = bool(
            fork_head and row["decision"] != "applied"
            and any(sha and sha != fork_head for sha in (row["analysis_sha"], row["fork_sha"]))
        )
        row["description"] = row["description"][:6000]
        return row

    def detail(self, commit_id: int) -> dict:
        with self.store.transaction() as db:
            row = db.execute(
                """
                SELECT c.* FROM dashboard_commits c JOIN dashboard_profiles p ON p.id = c.profile_id
                WHERE p.active = 1 AND c.id = ?
                """,
                (commit_id,),
            ).fetchone()
            if not row:
                raise ActionError("Commit does not belong to the active profile.")
            jobs = db.execute(
                f"SELECT {JOB_SUMMARY} FROM dashboard_jobs j WHERE j.commit_id = ? ORDER BY id DESC",
                (commit_id,),
            )
            events = db.execute(
                "SELECT action, created_at FROM dashboard_events WHERE commit_id = ? ORDER BY id DESC",
                (commit_id,),
            )
            commit = dict(row)
            commit["recommendation"] = recommendation(commit)
            return {"commit": commit, "jobs": [dict(job) for job in jobs], "events": [dict(event) for event in events]}

    def queue(self, query: dict) -> dict:
        page = page_number(query)
        profile = self.store.active_profile()
        if not profile:
            return {"jobs": [], "total": 0, "page_size": PAGE_SIZE, "page": page}
        profile_id = profile["id"]
        with self.store.transaction() as db:
            jobs = db.execute(
                f"""
                SELECT {JOB_SUMMARY}, c.subject FROM dashboard_jobs j
                LEFT JOIN dashboard_commits c ON j.commit_id = c.id
                WHERE j.profile_id = ?
                ORDER BY CASE WHEN j.status IN ('running', 'awaiting_confirmation', 'confirmed', 'committing')
                    THEN 0 WHEN j.status = 'queued' THEN 1 ELSE 2 END, j.id DESC
                LIMIT ? OFFSET ?
                """,
                (profile_id, PAGE_SIZE, page * PAGE_SIZE),
            )
            total = db.execute("SELECT count(*) FROM dashboard_jobs WHERE profile_id = ?", (profile_id,))
            return {
                "jobs": [dict(job) for job in jobs], "total": total.fetchone()[0],
                "page": page, "page_size": PAGE_SIZE,
            }

    def job(self, job_id: int) -> dict:
        with self.store.transaction() as db:
            return dict(current_job(db, job_id))


def page_number(query: dict) -> int:
    try:
        return min(1_000_000, max(0, int(query.get("page", ["0"])[0])))
    except ValueError as error:
        raise ActionError("Use a numeric page.") from error


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTP

    def log_message(self, format: str, *args) -> None:
        pass

    def _respond(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; font-src 'self'; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _json(self, data: dict, status: int = HTTPStatus.OK) -> None:
        self._respond(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _valid_host(self) -> bool:
        if self.headers.get("Host") != self.server.host_header:
            self._json({"error": "Use the dashboard's loopback address."}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def _authorized(self, *, write: bool = False) -> bool:
        provided = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(provided, f"Bearer {self.server.token}".encode()):
            self._json({"error": "Open the dashboard URL printed by the service."}, HTTPStatus.UNAUTHORIZED)
            return False
        if write and self.headers.get("Origin") != self.server.origin:
            self._json({"error": "Dashboard actions require the local origin."}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def do_GET(self) -> None:
        if not self._valid_host():
            return
        url = urlsplit(self.path)
        if not url.path.startswith("/api/"):
            self._asset(url.path)
            return
        if not self._authorized():
            return
        try:
            query = parse_qs(url.query, max_num_fields=8)
            if url.path == "/api/overview":
                self._json(self.server.overview(query))
            elif url.path == "/api/queue":
                self._json(self.server.queue(query))
            elif match := re.fullmatch(r"/api/commits/(\d{1,16})", url.path):
                self._json(self.server.detail(int(match[1])))
            elif match := re.fullmatch(r"/api/jobs/(\d{1,16})", url.path):
                self._json(self.server.job(int(match[1])))
            else:
                self._json({"error": "Page not found."}, HTTPStatus.NOT_FOUND)
        except (ValueError, sqlite3.Error) as error:
            self._client_error(error)

    def _asset(self, path: str) -> None:
        name = "index.html" if path == "/" else path.removeprefix("/assets/")
        content_type = STATIC_TYPES.get(Path(name).suffix)
        if not content_type or not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
            self._json({"error": "Page not found."}, HTTPStatus.NOT_FOUND)
            return
        asset = resources.files("backport_harness.dashboard").joinpath("assets", name)
        if not asset.is_file():
            self._json({"error": "Page not found."}, HTTPStatus.NOT_FOUND)
            return
        self._respond(HTTPStatus.OK, asset.read_bytes(), content_type)

    def _body(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise ActionError("Send a JSON request.")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_FORM_BYTES:
            raise ActionError("The request is empty or too large.")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ActionError("Send a JSON object.")
        return body

    def do_POST(self) -> None:
        if not self._valid_host() or not self._authorized(write=True):
            return
        try:
            self._post(urlsplit(self.path).path, self._body())
        except (ValueError, OSError, GitError, sqlite3.Error) as error:
            self._client_error(error)

    def _post(self, path: str, body: dict) -> None:
        store = self.server.store
        if path == "/api/profile":
            settings = self.server.worker.workspace.validate(ProfileSettings.model_validate(body))
            self._json({"profile_id": store.save_profile(settings)})
            return
        if path == "/api/pause":
            paused = body.get("paused")
            if type(paused) is not bool:
                raise ActionError("Choose pause or resume.")
            store.pause(paused)
            self._json({"paused": paused})
            return
        if path == "/api/scans":
            rescan = body.get("rescan", False)
            if type(rescan) is not bool:
                raise ActionError("Choose scan or rescan from the base.")
            job_id = store.scan_now(rescan=rescan)
        elif match := re.fullmatch(r"/api/commits/(\d{1,16})/(apply|adapt|analysis|skip|unskip)", path):
            prompt = body.get("prompt", "")
            if not isinstance(prompt, str) or len(prompt) > MAX_PROMPT:
                raise ActionError(f"Enter a prompt of at most {MAX_PROMPT} characters.")
            job_id = store.request_commit(int(match[1]), match[2], prompt)
        elif match := re.fullmatch(r"/api/jobs/(\d{1,16})/(cancel|retry|confirm)", path):
            job_id, action = int(match[1]), match[2]
            if action == "confirm":
                job_id = store.confirm(job_id, body.get("prepared_sha"))
            elif action == "cancel":
                job_id = store.cancel(job_id)
            else:
                job = self.server.job(job_id)
                if job["status"] == "committing" and job["error"]:
                    self.server.worker.recover_write(job)
                else:
                    job_id = store.retry(job_id)
        else:
            self._json({"error": "Action not found."}, HTTPStatus.NOT_FOUND)
            return
        self._json({"job_id": job_id or None}, HTTPStatus.ACCEPTED if job_id else HTTPStatus.OK)

    def _client_error(self, error: Exception) -> None:
        if isinstance(error, ValidationError):
            issue = error.errors(include_input=False, include_url=False, include_context=False)[0]
            message = f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}"
        elif isinstance(error, sqlite3.Error):
            logger.error("The dashboard could not read or write its database.")
            self._json({"error": "The dashboard database is temporarily unavailable."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        else:
            message = str(error)
        self._json({"error": message}, HTTPStatus.BAD_REQUEST)


@contextmanager
def service_lock(database: Path):
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = database.with_name(f"{database.name}.dashboard.lock")
    fd = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ActionError("A dashboard already serves this database.") from error
        initial = os.open(database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(initial, 0o600)
        finally:
            os.close(initial)
        yield


def serve(database: Path, state: Path, roots: list[Path], port: int, model: str, announce) -> None:
    database = database.resolve()
    state = state.resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with service_lock(database):
        database_key = hashlib.sha256(os.fsencode(database)).hexdigest()[:24]
        worker = DashboardWorker(
            DashboardStore(database), GitWorkspace(state / "git" / database_key, roots),
            StaticCodex(os.environ.get("OPENAI_API_KEY"), model),
        )
        with DashboardHTTP(port, worker) as server:
            worker.start()
            try:
                announce(server.launch_url)
                server.serve_forever()
            finally:
                worker.stop()
