from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backport_harness.dashboard.models import ProfileSettings, ScanBatch
from backport_harness.storage import connect, init_database


class ActionError(ValueError):
    pass


PROFILE_FIELDS = tuple(ProfileSettings.model_fields)
PROFILE_IDENTITY = ("upstream", "upstream_branch", "base_ref", "fork_path", "target_branch")
IN_PROGRESS = "('queued', 'running', 'awaiting_confirmation', 'confirmed', 'committing')"
LANES = {
    "scan": "j.kind IN ('scan', 'rescan') AND j.status = 'queued'",
    "git": """(j.kind IN ('probe', 'apply') AND j.status = 'queued'
                OR j.kind = 'adapt' AND j.status = 'confirmed')""",
    "codex": "j.kind IN ('analysis', 'adapt') AND j.status = 'queued'",
}


def profile_settings(row: sqlite3.Row | dict) -> ProfileSettings:
    return ProfileSettings.model_validate({name: row[name] for name in PROFILE_FIELDS})


def enqueue(
    db: sqlite3.Connection,
    profile_id: int,
    kind: str,
    commit_id: int | None = None,
    *,
    prompt: str = "",
    automatic: bool = False,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO dashboard_jobs (profile_id, commit_id, kind, token, automatic, prompt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (profile_id, commit_id, kind, uuid.uuid4().hex, automatic, prompt),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def active_id(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT id FROM dashboard_profiles WHERE active = 1").fetchone()
    if row is None:
        raise ActionError("Save a project profile first.")
    return row["id"]


def current_job(db: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    job = db.execute(
        "SELECT * FROM dashboard_jobs WHERE id = ? AND profile_id = ?", (job_id, active_id(db))
    ).fetchone()
    if job is None:
        raise ActionError("Job does not belong to the active profile.")
    return job


def set_job(db: sqlite3.Connection, job_id: int, status: str, **values) -> None:
    assignments = ", ".join(f"{column} = ?" for column in values)
    db.execute(
        f"UPDATE dashboard_jobs SET status = ?, updated_at = CURRENT_TIMESTAMP"
        f"{', ' + assignments if assignments else ''} WHERE id = ?",
        (status, *values.values(), job_id),
    )


class DashboardStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        init_database(path)
        with self.transaction() as db:
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                if write:
                    db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def active_profile(self) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM dashboard_profiles WHERE active = 1").fetchone()
            return dict(row) if row else None

    def save_profile(self, settings: ProfileSettings) -> int:
        data = settings.model_dump(mode="json")
        with self.transaction(write=True) as db:
            current = db.execute("SELECT * FROM dashboard_profiles WHERE active = 1").fetchone()
            if current and all(current[name] == data[name] for name in PROFILE_IDENTITY):
                db.execute(
                    """
                    UPDATE dashboard_profiles
                    SET interval_minutes = ?, match_words = ?, analysis_limit = ?,
                        analyses_left = min(analyses_left, ?), next_scan_at = 0
                    WHERE id = ?
                    """,
                    (
                        settings.interval_minutes, settings.match_words, settings.analysis_limit,
                        settings.analysis_limit, current["id"],
                    ),
                )
                return current["id"]

            if current and db.execute(
                """
                SELECT 1 FROM dashboard_jobs WHERE profile_id = ?
                    AND status IN ('running', 'confirmed', 'committing')
                """,
                (current["id"],),
            ).fetchone():
                raise ActionError("Wait for the active jobs before selecting another profile.")

            db.execute("UPDATE dashboard_profiles SET active = 0 WHERE active = 1")
            row = db.execute(
                """
                INSERT INTO dashboard_profiles (
                    upstream, upstream_branch, base_ref, fork_path, target_branch,
                    interval_minutes, match_words, analysis_limit
                ) VALUES (:upstream, :upstream_branch, :base_ref, :fork_path, :target_branch,
                          :interval_minutes, :match_words, :analysis_limit)
                ON CONFLICT (upstream, upstream_branch, base_ref, fork_path, target_branch)
                DO UPDATE SET active = 1, interval_minutes = excluded.interval_minutes,
                    match_words = excluded.match_words, analysis_limit = excluded.analysis_limit,
                    analyses_left = 0, next_scan_at = 0
                RETURNING id
                """,
                data,
            ).fetchone()
            return row["id"]

    @staticmethod
    def save_scan(db: sqlite3.Connection, profile_id: int, batch: ScanBatch) -> int:
        added = 0
        for commit in batch.commits:
            row = db.execute(
                """
                INSERT INTO dashboard_commits
                    (profile_id, sha, subject, description, committed_at, parent_count)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (profile_id, sha) DO NOTHING
                RETURNING id
                """,
                (
                    profile_id, commit.sha, commit.subject, commit.description,
                    commit.committed_at, len(commit.parents),
                ),
            ).fetchone()
            if row:
                enqueue(db, profile_id, "probe", row["id"], automatic=True)
                added += 1
        db.execute(
            """
            UPDATE dashboard_profiles SET cursor = ?, base_sha = ?, rewrite_detected = 0
            WHERE id = ?
            """,
            (batch.head, batch.base, profile_id),
        )
        return added

    def schedule(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.transaction(write=True) as db:
            profile = db.execute(
                """
                SELECT * FROM dashboard_profiles
                WHERE active = 1 AND paused = 0 AND rewrite_detected = 0 AND next_scan_at <= ?
                """,
                (now,),
            ).fetchone()
            if profile is None:
                return
            db.execute(
                """
                UPDATE dashboard_profiles SET next_scan_at = ?, analyses_left = analysis_limit
                WHERE id = ?
                """,
                (now + 60 * profile["interval_minutes"], profile["id"]),
            )
            self._scan_request(db, profile["id"], "scan", automatic=True)

    def pause(self, paused: bool) -> None:
        with self.transaction(write=True) as db:
            db.execute("UPDATE dashboard_profiles SET paused = ? WHERE id = ?", (paused, active_id(db)))

    def scan_now(self, *, rescan: bool = False) -> int:
        with self.transaction(write=True) as db:
            return self._scan_request(db, active_id(db), "rescan" if rescan else "scan")

    @staticmethod
    def _scan_request(db: sqlite3.Connection, profile_id: int, kind: str, *, automatic=False) -> int:
        duplicate = db.execute(
            """
            SELECT id, status, kind, automatic FROM dashboard_jobs
            WHERE profile_id = ? AND kind IN ('scan', 'rescan') AND status IN ('queued', 'running')
            """,
            (profile_id,),
        ).fetchone()
        if duplicate:
            if kind == "rescan" and duplicate["kind"] != "rescan" and duplicate["status"] == "running":
                raise ActionError("Wait for the current scan before rescanning from the base.")
            if not automatic and duplicate["status"] == "queued":
                db.execute(
                    "UPDATE dashboard_jobs SET kind = ?, automatic = 0 WHERE id = ?",
                    ("rescan" if kind == "rescan" else duplicate["kind"], duplicate["id"]),
                )
            return duplicate["id"]
        return enqueue(db, profile_id, kind, automatic=automatic)

    def claim(self, lane: str, *, codex_available: bool = True) -> dict | None:
        with self.transaction(write=True) as db:
            row = db.execute(
                f"""
                SELECT j.* FROM dashboard_jobs j JOIN dashboard_profiles p ON p.id = j.profile_id
                WHERE p.active = 1 AND {LANES[lane]}
                    AND (j.automatic = 0 OR p.paused = 0)
                    AND (j.automatic = 0 OR j.kind != 'analysis' OR (
                        p.analyses_left > 0 AND ? AND EXISTS (
                            SELECT 1 FROM dashboard_commits c
                            WHERE c.id = j.commit_id AND c.decision IS NULL
                        )
                    ))
                ORDER BY j.automatic, j.id LIMIT 1
                """,
                (codex_available,),
            ).fetchone()
            if row is None:
                return None
            set_job(db, row["id"], "running")
            if row["kind"] == "analysis" and row["automatic"]:
                db.execute(
                    "UPDATE dashboard_profiles SET analyses_left = analyses_left - 1 WHERE id = ?",
                    (row["profile_id"],),
                )
            return dict(row)

    def request_commit(self, commit_id: int, kind: str, prompt: str = "") -> int:
        with self.transaction(write=True) as db:
            profile_id = active_id(db)
            commit = db.execute(
                "SELECT * FROM dashboard_commits WHERE id = ? AND profile_id = ?",
                (commit_id, profile_id),
            ).fetchone()
            if commit is None:
                raise ActionError("Commit does not belong to the active profile.")
            if kind in {"skip", "unskip"}:
                return self._review(db, commit, kind)
            if kind not in {"apply", "adapt", "analysis"}:
                raise ActionError("Unknown commit action.")
            duplicate = db.execute(
                f"""
                SELECT id, kind, status, automatic FROM dashboard_jobs
                WHERE commit_id = ?
                  AND (kind = ? OR (kind IN ('apply', 'adapt') AND ? IN ('apply', 'adapt')))
                  AND (status IN {IN_PROGRESS} OR (? = 'applied' AND kind IN ('apply', 'adapt')
                       AND status = 'succeeded' AND prepared_sha IS NOT NULL))
                ORDER BY id DESC LIMIT 1
                """,
                (commit_id, kind, kind, commit["decision"]),
            ).fetchone()
            if duplicate:
                if kind == "analysis" and duplicate["status"] == "queued" and duplicate["automatic"]:
                    db.execute(
                        "UPDATE dashboard_jobs SET automatic = 0, prompt = ? WHERE id = ?",
                        (prompt, duplicate["id"]),
                    )
                return duplicate["id"]
            if commit["decision"] == "skipped" and kind in {"apply", "adapt"}:
                raise ActionError("Undo Skip before applying this commit.")
            return enqueue(db, profile_id, kind, commit_id, prompt=prompt)

    @staticmethod
    def _review(db: sqlite3.Connection, commit: sqlite3.Row, action: str) -> int:
        if commit["decision"] == "applied" or db.execute(
            f"""
            SELECT 1 FROM dashboard_jobs WHERE commit_id = ? AND kind IN ('apply', 'adapt')
                AND status IN {IN_PROGRESS}
            """,
            (commit["id"],),
        ).fetchone():
            raise ActionError("Skip cannot change an applied or in-progress fix.")
        decision = "skipped" if action == "skip" else None
        if commit["decision"] != decision:
            db.execute("UPDATE dashboard_commits SET decision = ? WHERE id = ?", (decision, commit["id"]))
            db.execute(
                "INSERT INTO dashboard_events (commit_id, action) VALUES (?, ?)",
                (commit["id"], action),
            )
        return 0

    def confirm(self, job_id: int, prepared_sha: str) -> int:
        with self.transaction(write=True) as db:
            job = current_job(db, job_id)
            if not prepared_sha or prepared_sha != job["prepared_sha"] or job["kind"] != "adapt":
                raise ActionError("Confirm the SHA of the prepared patch.")
            if job["status"] == "awaiting_confirmation":
                set_job(db, job_id, "confirmed")
            elif job["status"] not in {"confirmed", "running", "committing", "succeeded"}:
                raise ActionError("The prepared patch is no longer ready for confirmation.")
            return job_id

    def cancel(self, job_id: int) -> int:
        with self.transaction(write=True) as db:
            job = current_job(db, job_id)
            if job["status"] in {"queued", "awaiting_confirmation", "confirmed"}:
                set_job(db, job_id, "canceled", cancel_requested=1)
            elif job["status"] == "running":
                set_job(db, job_id, "running", cancel_requested=1)
            elif job["status"] != "canceled":
                raise ActionError("This job can no longer be canceled.")
            return job_id

    def retry(self, job_id: int) -> int:
        with self.transaction(write=True) as db:
            job = current_job(db, job_id)
            if job["status"] not in {"failed", "canceled", "stale"}:
                raise ActionError("Only failed, canceled, or stale jobs can be retried.")
            if job["kind"] in {"scan", "rescan"}:
                return self._scan_request(db, job["profile_id"], job["kind"])
            duplicate = db.execute(
                f"""
                SELECT id FROM dashboard_jobs WHERE commit_id = ?
                  AND (kind = ? OR (kind IN ('apply', 'adapt') AND ? IN ('apply', 'adapt')))
                  AND status IN {IN_PROGRESS} ORDER BY id LIMIT 1
                """,
                (job["commit_id"], job["kind"], job["kind"]),
            ).fetchone()
            if duplicate:
                return duplicate["id"]
            if job["kind"] in {"apply", "adapt"}:
                decision = db.execute(
                    "SELECT decision FROM dashboard_commits WHERE id = ?", (job["commit_id"],)
                ).fetchone()["decision"]
                if decision:
                    raise ActionError("The operator already made a decision for this commit.")
            return enqueue(
                db, job["profile_id"], job["kind"], job["commit_id"], prompt=job["prompt"]
            )
