# List Saved PRs

## Goal

Add a CLI view for saved PRs so users can decide what to analyze before spending Codex runs.

## Implementation Scope

- Add `backport-harness list-prs`.
- Read saved PRs from SQLite without contacting GitHub.
- Join saved PR rows with their analysis queue row and latest stored decision.
- Render a concise terminal table suitable for choosing analysis candidates.
- Support filters for branch, queue status, merged date range, and limit.
- Support ordering by merged date, branch, priority, or queue status.

## Expected Behavior

- `backport-harness list-prs` shows saved PRs.
- `--branch` filters by saved PR target branch.
- `--status` filters by analysis queue status.
- `--from-date` and `--to-date` filter by `prs.merged_at` using `YYYY-MM-DD`.
- `--limit` restricts the number of displayed rows and must be positive.
- `--order-by` accepts `merged-at`, `branch`, `priority`, or `status`.
- Empty results display a short no-results message.
- Output is readable for selecting analysis candidates.

## Affected Modules or Commands

- `backport_harness/commands/list_prs.py`
- Storage query helpers
- Command: `backport-harness list-prs`

## Test Plan

- Cover empty DB output.
- Cover branch filter.
- Cover status filter.
- Cover date filter.
- Cover limit validation and limiting behavior.
- Cover ordering by merged date, branch, priority, and status.
- Cover display of the latest decision when multiple decisions exist.
- Cover CLI help and invalid date handling.

## Assumptions and Explicit Non-goals

- This command reads SQLite only.
- This command does not scan GitHub or invoke Codex.
- This command does not mutate queue status, decisions, PR metadata, or files.
- JSON output is out of scope for this milestone.
- `inspect --pr` is out of scope for this milestone.
