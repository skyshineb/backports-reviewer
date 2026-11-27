from __future__ import annotations

import json
import logging
import sqlite3
import threading

from backport_harness.dashboard.codex import Adaptation, CodexError, JobCanceled, Review, Snapshot, StaticCodex
from backport_harness.dashboard.git import GitError, GitWorkspace, StalePatch, UpstreamRewrite
from backport_harness.dashboard.models import PreparedPatch, ProfileSettings
from backport_harness.dashboard.store import DashboardStore, IN_PROGRESS, enqueue, profile_settings, set_job

logger = logging.getLogger(__name__)


class DashboardWorker:
    def __init__(self, store: DashboardStore, workspace: GitWorkspace, codex: StaticCodex) -> None:
        self.store = store
        self.workspace = workspace
        self.codex = codex
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.recover()
        self._stop.clear()
        for lane in ("scan", "git", "codex"):
            thread = threading.Thread(target=self._loop, args=(lane,), name=f"dashboard-{lane}", daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=1)

    def _loop(self, lane: str) -> None:
        while not self._stop.is_set():
            try:
                if lane == "scan":
                    self.store.schedule()
                if self.run_next(lane):
                    continue
            except Exception:
                # Keep worker infrastructure alive without logging private task output.
                logger.error("Dashboard %s worker could not update its durable job state.", lane)
            self._stop.wait(0.5)

    def run_next(self, lane: str) -> bool:
        job = self.store.claim(lane, codex_available=self.codex.available)
        if not job:
            return False
        with self.store.transaction() as db:
            profile = dict(db.execute(
                "SELECT * FROM dashboard_profiles WHERE id = ?", (job["profile_id"],)
            ).fetchone())
            candidate = db.execute("SELECT * FROM dashboard_commits WHERE id = ?", (job["commit_id"],)).fetchone()
        settings = profile_settings(profile)
        try:
            if job["status"] == "confirmed":
                patch = PreparedPatch(job["expected_sha"], job["prepared_sha"], job["diff"])
                self._promote(job, settings, patch)
            elif job["kind"] in {"scan", "rescan"}:
                self._scan(job, profile, settings)
            else:
                self._process_commit(job, dict(candidate), settings)
        except JobCanceled:
            self._fail(job, "canceled", None)
        except UpstreamRewrite as error:
            with self.store.transaction(write=True) as db:
                db.execute("UPDATE dashboard_profiles SET rewrite_detected = 1 WHERE id = ?", (profile["id"],))
                set_job(db, job["id"], "failed", error=str(error))
        except StalePatch as error:
            self._fail(job, "stale", str(error))
        except (GitError, CodexError, OSError, ValueError) as error:
            self._fail(job, "failed", str(error))
        except Exception:
            self._fail(job, "failed", "The worker was interrupted while handling this job.")
        return True

    def _scan(self, job: dict, profile: dict, settings: ProfileSettings) -> None:
        cursor = profile["cursor"] if job["kind"] == "scan" else None
        batch = self.workspace.scan(profile["id"], settings, cursor, profile["base_sha"])
        with self.store.transaction(write=True) as db:
            self._check_canceled(db, job["id"])
            added = self.store.save_scan(db, profile["id"], batch)
            set_job(db, job["id"], "succeeded", result=json.dumps({"new_commits": added, "head": batch.head}))

    def _process_commit(self, job: dict, commit: dict, settings: ProfileSettings) -> None:
        profile_id = job["profile_id"]
        target = self.workspace.snapshot(profile_id, settings)
        with self.store.transaction(write=True) as db:
            self._check_canceled(db, job["id"])
            set_job(db, job["id"], "running", expected_sha=target)
        kind = job["kind"]
        if kind == "probe":
            state = self.workspace.probe(profile_id, target, commit["sha"], commit["parent_count"])
            self._save_probe(job, commit, target, state)
            return
        if kind == "analysis":
            reviewed = self._codex(job, commit, target, adapt=False)
            if not isinstance(reviewed, Review):
                raise CodexError("The worker returned the wrong result type.")
            with self.store.transaction(write=True) as db:
                self._check_canceled(db, job["id"])
                db.execute(
                    """
                    UPDATE dashboard_commits SET analysis_sha = ?, relevance = ?, severity = ?, notes = ?
                    WHERE id = ?
                    """,
                    (target, reviewed.relevance, reviewed.severity, reviewed.notes, commit["id"]),
                )
                set_job(db, job["id"], "succeeded", result=reviewed.model_dump_json())
            return

        state, patch = self.workspace.prepare_pick(profile_id, target, commit, job["token"])
        if state == "empty" or (state == "conflict" and kind == "apply"):
            self._save_probe(job, commit, target, state)
            return
        if kind == "apply":
            assert patch is not None
            self._promote(job, settings, patch)
            return
        notes = "A clean pick is available on the current target."
        if patch is None:
            adapted = self._codex(job, commit, target, adapt=True)
            if not isinstance(adapted, Adaptation):
                raise CodexError("The worker returned the wrong result type.")
            patch = self.workspace.prepare_adaptation(profile_id, target, commit, job["token"], adapted.patch)
            notes = adapted.notes
        with self.store.transaction(write=True) as db:
            self._check_canceled(db, job["id"])
            db.execute(
                "UPDATE dashboard_commits SET applicability = ?, fork_sha = ? WHERE id = ?",
                (state, target, commit["id"]),
            )
            set_job(
                db, job["id"], "awaiting_confirmation", expected_sha=patch.expected_sha,
                prepared_sha=patch.sha, diff=patch.diff, result=json.dumps({"notes": notes}),
            )

    def _codex(self, job: dict, commit: dict, target: str, *, adapt: bool) -> Review | Adaptation:
        return self.codex.run(
            Snapshot(self.workspace.mirror(job["profile_id"]), target),
            self.workspace.source_diff(job["profile_id"], commit["sha"]),
            job["prompt"],
            adapt=adapt,
            canceled=lambda: self._is_canceled(job["id"]),
        )

    def _save_probe(self, job: dict, commit: dict, target: str, state: str) -> None:
        with self.store.transaction(write=True) as db:
            self._check_canceled(db, job["id"])
            current = db.execute("SELECT * FROM dashboard_commits WHERE id = ?", (commit["id"],)).fetchone()
            db.execute(
                "UPDATE dashboard_commits SET applicability = ?, fork_sha = ? WHERE id = ?",
                (state, target, commit["id"]),
            )
            set_job(db, job["id"], "succeeded", result=json.dumps({"applicability": state}))
            if job["kind"] == "probe" and state == "conflict" and not current["decision"] and not db.execute(
                f"SELECT 1 FROM dashboard_jobs WHERE commit_id = ? AND kind = 'analysis' AND status IN {IN_PROGRESS}",
                (commit["id"],),
            ).fetchone():
                enqueue(db, job["profile_id"], "analysis", commit["id"], automatic=True)

    def _promote(self, job: dict, settings: ProfileSettings, patch: PreparedPatch) -> None:
        with self.store.transaction(write=True) as db:
            self._check_canceled(db, job["id"])
            set_job(
                db, job["id"], "committing", expected_sha=patch.expected_sha,
                prepared_sha=patch.sha, diff=patch.diff,
            )
        self.workspace.promote(job["profile_id"], settings, job["token"], patch)
        with self.store.transaction(write=True) as db:
            self._record_application(db, job | {"expected_sha": patch.expected_sha}, patch.sha)

    @staticmethod
    def _record_application(db: sqlite3.Connection, job: dict | sqlite3.Row, sha: str) -> None:
        db.execute(
            """
            UPDATE dashboard_commits SET decision = 'applied', applied_sha = ?, fork_sha = ?,
                applicability = CASE WHEN ? = 'apply' THEN 'applicable' ELSE applicability END
            WHERE id = ?
            """,
            (sha, job["expected_sha"], job["kind"], job["commit_id"]),
        )
        db.execute("INSERT INTO dashboard_events (commit_id, action) VALUES (?, 'applied')", (job["commit_id"],))
        set_job(db, job["id"], "succeeded", error=None)

    def _is_canceled(self, job_id: int) -> bool:
        with self.store.transaction() as db:
            return self._stop.is_set() or bool(db.execute(
                "SELECT cancel_requested FROM dashboard_jobs WHERE id = ?", (job_id,)
            ).fetchone()[0])

    def _check_canceled(self, db: sqlite3.Connection, job_id: int) -> None:
        if db.execute("SELECT cancel_requested FROM dashboard_jobs WHERE id = ?", (job_id,)).fetchone()[0]:
            raise JobCanceled()

    def _fail(self, job: dict, status: str, error: str | None) -> None:
        current = None
        with self.store.transaction(write=True) as db:
            row = db.execute("SELECT * FROM dashboard_jobs WHERE id = ?", (job["id"],)).fetchone()
            if row["status"] == "committing":
                current = dict(row)
            else:
                if self._stop.is_set() and status == "canceled" and not row["cancel_requested"]:
                    status = "confirmed" if job["status"] == "confirmed" else "queued"
                if row["cancel_requested"]:
                    status, error = "canceled", None
                set_job(db, job["id"], status, error=error)
                if job["kind"] == "probe" and status == "failed":
                    db.execute("UPDATE dashboard_commits SET applicability = 'error' WHERE id = ?", (job["commit_id"],))
        if current:
            self._reconcile(current, status, error)

    def _reconcile(self, job: dict, status: str, error: str | None) -> None:
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM dashboard_profiles WHERE id = ?", (job["profile_id"],)).fetchone()
        try:
            marker = self.workspace.applied_marker(profile_settings(row), job["token"])
        except (GitError, ValueError, OSError):
            with self.store.transaction(write=True) as db:
                set_job(db, job["id"], "committing", error="Cannot check Git write. Restore fork access and retry recovery.")
            return
        with self.store.transaction(write=True) as db:
            current = db.execute("SELECT status FROM dashboard_jobs WHERE id = ?", (job["id"],)).fetchone()
            if current["status"] != "committing":
                return
            if marker and marker == job["prepared_sha"]:
                self._record_application(db, job, marker)
            else:
                set_job(db, job["id"], status, error=error)

    def recover(self) -> None:
        with self.store.transaction(write=True) as db:
            db.execute(
                """
                UPDATE dashboard_jobs SET status = CASE
                    WHEN cancel_requested = 1 THEN 'canceled'
                    WHEN kind = 'adapt' AND prepared_sha IS NOT NULL THEN 'confirmed'
                    ELSE 'queued' END
                WHERE status = 'running'
                """
            )
            interrupted = list(db.execute("SELECT * FROM dashboard_jobs WHERE status = 'committing'"))
        for job in interrupted:
            self.recover_write(dict(job))

    def recover_write(self, job: dict) -> None:
        self._reconcile(job, "failed", "Interrupted before recording the Git write. Retry the operation.")
