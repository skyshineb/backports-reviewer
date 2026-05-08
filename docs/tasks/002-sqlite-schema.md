# SQLite Schema and Migrations

## Goal

Create durable SQLite storage and idempotent migrations for the core data model defined in the design docs.

## Implementation Scope

TBD from design docs before implementation. This milestone should cover `storage.py`, a migration runner, and the initial migration for PRs, files, scan runs, queue rows, analysis runs, decisions, evidence, test runs, and human reviews.

## Expected Behavior

- `backport-harness db init` creates the database file.
- Migrations are idempotent.
- Running migration twice is safe.

## Affected Modules or Commands

- `backport_harness/storage.py`
- `backport_harness/migrations/001_initial.sql`
- Command: `backport-harness db init`

## Test Plan

TBD. At minimum, verify the database file is created, required tables exist, and migrations can be rerun safely.

## Assumptions and Explicit Non-goals

- SQLite is the source of truth.
- Do not implement this milestone until the task is expanded and checked against the design docs.
- This milestone does not scan GitHub or invoke Codex.

