# Slow GitHub Scanner

## Goal

Implement polite, idempotent scanning of public upstream GitHub PRs merged into configured branches and date ranges.

## Implementation Scope

- Add a public GitHub API client for the configured upstream repository.
- Query merged pull requests by base branch and `merged_at` date range.
- Fetch canonical PR metadata and changed files for every scanned PR.
- Store or update PR metadata in SQLite.
- Refresh changed-file rows for each saved PR.
- Create missing `analysis_queue` rows without overwriting existing queue state.
- Record one `scan_runs` audit row per scanned branch.
- Add the `backport-harness scan` CLI command with date and optional branch filters.
- Respect configured request delay, page delay, rate-limit handling, and retry backoff.

## Expected Behavior

- `backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31` scans by `merged_at`.
- Branch filter is optional; omitted branch scans both configured branches.
- A provided branch must be present in `github.branches`.
- Re-running a scan does not duplicate data or lose queue state.
- Scanner respects configured request and page delays.
- Scan failures are recorded in `scan_runs.last_error`.
- Scanning never invokes Codex or creates local worktrees.

## Affected Modules or Commands

- `backport_harness/github_client.py`
- `backport_harness/scanner.py`
- Scan command module
- SQLite storage helpers
- Command: `backport-harness scan`

## Test Plan

- Use mocked GitHub API/session responses only; tests must not require real network access or a GitHub token.
- Cover one-branch scans and omitted-branch scans over all configured branches.
- Cover `from-date` only and `from-date` plus `to-date` query construction.
- Cover changed-file capture and deterministic file classification flags.
- Cover idempotent rescan behavior for PRs, PR files, and queue rows.
- Cover failed scan audit rows.
- Cover retry and backoff behavior for `403`, `429`, and `5xx`.
- Cover rate-limit reset handling from GitHub response headers.
- Cover CLI parsing and branch validation.

## Assumptions and Explicit Non-goals

- The scanner only uses public upstream metadata and diffs.
- The existing SQLite schema is sufficient for this milestone.
- Use optional GitHub authentication only through the configured token environment variable.
- Scanning must not invoke Codex.
- Scanning must not clone repositories, create worktrees, list saved PRs, inspect PRs, analyze PRs, retry analysis, or generate reports.
