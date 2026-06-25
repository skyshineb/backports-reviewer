# Report Writer

## Goal

Generate human-readable and machine-readable reports from SQLite decisions and evidence.

## Implementation Scope

- Implement report generation from SQLite-backed PR, queue, decision, evidence, and human review data.
- Add a `backport-harness report` command that writes reports to the configured `reports.output_dir`.
- Generate:
  - `backport-candidates.md`
  - `inconclusive.md`
  - `discarded.jsonl`
  - `full-audit.jsonl`
- Include `MASTER_POSSIBLY_APPLICABLE` in backport candidates because it is a reportable decision that needs human review.
- Include queue-only `NEEDS_RETRY` rows in `inconclusive.md` when no latest decision exists.
- Make report regeneration deterministic and overwrite stale report files.

## Expected Behavior

- Reports can be regenerated at any time from SQLite.
- Markdown reports are readable.
- JSONL reports are machine-readable.
- Human review status is included when present.
- Report generation does not invoke Codex and does not use temporary task directories as the source of truth.
- Full audit output includes every PR, all stored decisions, evidence for those decisions, queue metadata, and latest human review status.

## Affected Modules or Commands

- `backport_harness/report_writer.py`
- Report command module
- Command: `backport-harness report`

## Test Plan

- Cover empty report generation.
- Cover backport candidate, inconclusive, discarded, and full-audit categories.
- Cover `MASTER_POSSIBLY_APPLICABLE` as a candidate.
- Cover queue-only `NEEDS_RETRY` rows.
- Cover latest decision selection for category reports.
- Cover full audit including multiple decisions and evidence.
- Cover human review status in Markdown and JSONL.
- Cover JSONL validity.
- Cover regeneration after decision changes.
- Cover CLI command registration and configured output directory usage.

## Assumptions and Explicit Non-goals

- Reports may link to logs and patches, but core metadata must come from SQLite.
- This task reads human review rows when present but does not implement the review command.
- This task does not access GitHub, Codex, public worktrees, private forks, private patches, or private test results.
