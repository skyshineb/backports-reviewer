# Slow GitHub Scanner

## Goal

Implement polite, idempotent scanning of public upstream GitHub PRs merged into configured branches and date ranges.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement the public GitHub client, merged PR scan, changed-file capture, scan audit records, analysis queue row creation, delays, rate-limit handling, and retry backoff.

## Expected Behavior

- `backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31` scans by `merged_at`.
- Branch filter is optional; omitted branch scans both configured branches.
- Re-running a scan does not duplicate data or lose queue state.
- Scanner respects configured request and page delays.

## Affected Modules or Commands

- `backport_harness/github_client.py`
- Scan command module
- SQLite storage helpers
- Command: `backport-harness scan`

## Test Plan

TBD. At minimum, use mocked GitHub API responses for one branch, both branches, changed files, date filters, idempotent re-scan, and rate-limit responses.

## Assumptions and Explicit Non-goals

- The scanner only uses public upstream metadata and diffs.
- Do not implement this milestone until the task is expanded and checked against the design docs.
- Scanning must not invoke Codex.

