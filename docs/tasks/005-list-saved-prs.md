# List Saved PRs

## Goal

Add a CLI view for saved PRs so users can decide what to analyze before spending Codex runs.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement `list-prs`, filtering, ordering, and a concise table joined from PR, queue, and latest decision data.

## Expected Behavior

- `backport-harness list-prs` shows saved PRs.
- Filters work for branch, queue status, merged date range, and limit.
- Output is readable for selecting analysis candidates.

## Affected Modules or Commands

- `backport_harness/commands/list_prs.py`
- Storage query helpers
- Command: `backport-harness list-prs`

## Test Plan

TBD. At minimum, cover empty DB output, branch filter, status filter, date filter, limit, and display of latest decision when present.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- This command reads SQLite only.
- This command does not scan GitHub or invoke Codex.

