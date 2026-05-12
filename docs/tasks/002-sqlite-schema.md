# SQLite Schema and Migrations

## Goal

Create durable SQLite storage and idempotent migrations for the core data model defined in the design docs.

## Implementation Scope

- Add `backport_harness/storage.py` with SQLite connection helpers and an idempotent migration runner.
- Add `backport_harness/migrations/001_initial.sql` with the initial schema from `docs/backport_harness_design.md` sections 7.1 through 7.9.
- Track applied migrations in a local `schema_migrations` table.
- Create these domain tables:
  - `prs`
  - `pr_files`
  - `scan_runs`
  - `analysis_queue`
  - `analysis_runs`
  - `decisions`
  - `evidence`
  - `test_runs`
  - `human_reviews`
- Add the `backport-harness db init` command.
- Resolve the database path from `storage.sqlite_path` in the existing YAML config dict, with `./workspace/backport_harness.sqlite3` as the fallback until milestone 003 adds strict config validation.

## Expected Behavior

- `backport-harness db init` creates the database file.
- Migrations are idempotent.
- Running migration twice is safe.

## Affected Modules or Commands

- `backport_harness/storage.py`
- `backport_harness/migrations/001_initial.sql`
- Command: `backport-harness db init`

## Test Plan

- Unit test that database initialization creates the database file and parent directory.
- Unit test that all required tables exist after initialization.
- Unit test that migrations can be rerun safely without duplicating migration records.
- Unit test that storage connections enable SQLite foreign-key enforcement.
- CLI test that `backport-harness db init` creates the configured database file and remains safe when rerun.

## Assumptions and Explicit Non-goals

- SQLite is the source of truth.
- The schema follows the current design docs; later milestones may add helpers and indexes for concrete workflows.
- This milestone uses Python's standard `sqlite3` module.
- This milestone does not add optional `db migrate` or `db status` commands.
- This milestone does not scan GitHub or invoke Codex.
- This milestone does not implement list, inspect, queue transition, decision storage, or human review commands.
