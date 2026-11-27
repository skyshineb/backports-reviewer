from __future__ import annotations

import sqlite3
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


def profile_settings(row: sqlite3.Row) -> ProfileSettings:
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
