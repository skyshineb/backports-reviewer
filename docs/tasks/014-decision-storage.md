# Decision Storage

## Goal

Persist validated Codex decisions, evidence, and test-run data in SQLite while preserving prior analysis attempts for audit.

## Implementation Scope

- Store validated Codex result data in `decisions`, `evidence`, and `test_runs`.
- Link decisions to the corresponding `analysis_runs` row.
- Preserve previous decisions and analysis runs.
- Update queue status to `REPORTABLE`, `DONE`, `NEEDS_RETRY`, or `FAILED_INFRA` based on validated outcome.
- Keep the latest decision easy to query for list, inspect, and report commands.

## Expected Behavior

- A valid Codex result becomes a stored decision.
- Evidence rows and test run rows are stored.
- Previous analysis attempts remain accessible.
- Queue status reflects the validated result.

## Affected Modules or Commands

- Storage helpers for decisions, evidence, and test runs
- Analysis integration after result validation
- List, inspect, and report query helpers

## Test Plan

- Store a valid decision and verify linked evidence/test rows.
- Verify previous decisions are preserved after a later run.
- Verify latest-decision query returns the newest stored decision.
- Verify queue status updates for reportable, done, retry, and infra-failed outcomes.

## Assumptions and Explicit Non-goals

- SQLite remains the source of truth.
- Reports must read stored decisions, not temporary Codex output.
- This milestone does not define result schema or validation rules.

