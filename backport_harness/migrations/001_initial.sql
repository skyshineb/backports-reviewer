CREATE TABLE IF NOT EXISTS prs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_pr_number INTEGER NOT NULL,
    github_pr_url TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    source_branch TEXT,
    target_branch TEXT NOT NULL,
    merged_commit_sha TEXT,
    created_at TEXT,
    updated_at TEXT,
    closed_at TEXT,
    merged_at TEXT NOT NULL,
    author TEXT,
    created_in_db_at TEXT NOT NULL,
    updated_in_db_at TEXT NOT NULL,
    UNIQUE(github_pr_number, target_branch)
);

CREATE TABLE IF NOT EXISTS pr_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    status TEXT,
    additions INTEGER,
    deletions INTEGER,
    is_test_file INTEGER NOT NULL DEFAULT 0,
    is_docs_file INTEGER NOT NULL DEFAULT 0,
    is_ci_file INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(pr_id) REFERENCES prs(id)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    prs_seen INTEGER DEFAULT 0,
    prs_saved INTEGER DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS analysis_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    locked_at TEXT,
    locked_by TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pr_id) REFERENCES prs(id),
    UNIQUE(pr_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    codex_exit_code INTEGER,
    status TEXT NOT NULL,
    task_dir TEXT NOT NULL,
    result_json_path TEXT,
    notes_path TEXT,
    stdout_log_path TEXT,
    stderr_log_path TEXT,
    FOREIGN KEY(pr_id) REFERENCES prs(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    analysis_run_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    confidence TEXT NOT NULL,
    bugfix_classification TEXT,
    applies_to_oss_015 INTEGER,
    reason TEXT NOT NULL,
    human_action TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(pr_id) REFERENCES prs(id),
    FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    description TEXT NOT NULL,
    file_path TEXT,
    command TEXT,
    exit_code INTEGER,
    log_path TEXT,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_run_id INTEGER NOT NULL,
    phase TEXT NOT NULL,
    command TEXT,
    exit_code INTEGER,
    result TEXT NOT NULL,
    log_path TEXT,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    reviewer TEXT,
    comment TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pr_id) REFERENCES prs(id)
);

CREATE INDEX IF NOT EXISTS idx_prs_target_branch_merged_at
    ON prs(target_branch, merged_at);

CREATE INDEX IF NOT EXISTS idx_pr_files_pr_id
    ON pr_files(pr_id);

CREATE INDEX IF NOT EXISTS idx_analysis_queue_status_priority
    ON analysis_queue(status, priority, id);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_pr_id
    ON analysis_runs(pr_id);

CREATE INDEX IF NOT EXISTS idx_decisions_pr_id
    ON decisions(pr_id);

CREATE INDEX IF NOT EXISTS idx_decisions_analysis_run_id
    ON decisions(analysis_run_id);

CREATE INDEX IF NOT EXISTS idx_evidence_decision_id
    ON evidence(decision_id);

CREATE INDEX IF NOT EXISTS idx_test_runs_analysis_run_id
    ON test_runs(analysis_run_id);

CREATE INDEX IF NOT EXISTS idx_human_reviews_pr_id
    ON human_reviews(pr_id);
