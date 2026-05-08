# Report Writer

## Goal

Generate human-readable and machine-readable reports from SQLite decisions and evidence.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement `report` and generate backport candidates, inconclusive, discarded, and full-audit outputs.

## Expected Behavior

- Reports can be regenerated at any time from SQLite.
- Markdown reports are readable.
- JSONL reports are machine-readable.
- Human review status is included when present.

## Affected Modules or Commands

- `backport_harness/report_writer.py`
- Report command module
- Command: `backport-harness report`

## Test Plan

TBD. At minimum, cover report categories, empty reports, human review status, JSONL validity, and regeneration after decision changes.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- Reports may link to logs and patches, but core metadata must come from SQLite.

