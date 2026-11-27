CREATE TABLE IF NOT EXISTS dashboard_profiles (
    id INTEGER PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    upstream TEXT NOT NULL,
    upstream_branch TEXT NOT NULL,
    base_ref TEXT NOT NULL,
    fork_path TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    match_words TEXT NOT NULL,
    analysis_limit INTEGER NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0, 1)),
    cursor TEXT,
    base_sha TEXT,
    rewrite_detected INTEGER NOT NULL DEFAULT 0,
    next_scan_at REAL NOT NULL DEFAULT 0,
    analyses_left INTEGER NOT NULL DEFAULT 0,
    UNIQUE (upstream, upstream_branch, base_ref, fork_path, target_branch)
);

CREATE UNIQUE INDEX IF NOT EXISTS dashboard_active_profile
    ON dashboard_profiles(active) WHERE active = 1;

CREATE TABLE IF NOT EXISTS dashboard_commits (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES dashboard_profiles(id),
    sha TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    parent_count INTEGER NOT NULL,
    applicability TEXT NOT NULL DEFAULT 'pending',
    fork_sha TEXT,
    analysis_sha TEXT,
    relevance TEXT,
    severity TEXT,
    notes TEXT,
    decision TEXT CHECK (decision IN ('skipped', 'applied')),
    applied_sha TEXT,
    UNIQUE (profile_id, sha)
);

CREATE INDEX IF NOT EXISTS dashboard_timeline ON dashboard_commits(profile_id, committed_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS dashboard_jobs (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES dashboard_profiles(id),
    commit_id INTEGER REFERENCES dashboard_commits(id),
    kind TEXT NOT NULL CHECK (kind IN ('scan', 'rescan', 'probe', 'analysis', 'apply', 'adapt')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'running', 'awaiting_confirmation', 'confirmed', 'committing',
        'succeeded', 'failed', 'canceled', 'stale'
    )),
    token TEXT NOT NULL UNIQUE,
    automatic INTEGER NOT NULL DEFAULT 0 CHECK (automatic IN (0, 1)),
    prompt TEXT NOT NULL DEFAULT '',
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    expected_sha TEXT,
    prepared_sha TEXT,
    diff TEXT,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS dashboard_job_queue ON dashboard_jobs(profile_id, status, kind, id);
CREATE INDEX IF NOT EXISTS dashboard_commit_jobs ON dashboard_jobs(commit_id, id DESC);

CREATE TABLE IF NOT EXISTS dashboard_events (
    id INTEGER PRIMARY KEY,
    commit_id INTEGER NOT NULL REFERENCES dashboard_commits(id),
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
