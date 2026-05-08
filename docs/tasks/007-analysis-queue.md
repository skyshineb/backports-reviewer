# Analysis Queue and Priority

## Goal

Implement deterministic queue state and dry-run analysis selection so expensive Codex analysis can be planned without running it.

## Implementation Scope

- Implement queue state transitions in `state_machine.py`.
- Assign initial priority using the documented priority rules.
- Select queued PRs by priority and date.
- Implement `backport-harness analyze --limit N --dry-run`.
- Ensure completed, paused, running, and failed rows are not selected incorrectly.
- Keep database state changes short and explicit.

## Expected Behavior

- Queue rows created by scanning can be selected for analysis.
- Dry run lists selected PRs without invoking Codex, creating task bundles, or touching worktrees.
- Higher-priority PRs are selected first.
- Already completed PRs are skipped.

## Affected Modules or Commands

- `backport_harness/state_machine.py`
- Analyze command dry-run path
- Storage queue helpers
- Command: `backport-harness analyze --limit 10 --dry-run`

## Test Plan

- Verify allowed and rejected queue transitions.
- Verify initial priority assignment for `0.15`, likely bugfix master PRs, ambiguous PRs, and default PRs.
- Verify dry-run ordering and limit behavior.
- Verify completed and paused rows are skipped.

## Assumptions and Explicit Non-goals

- This milestone does not invoke Codex.
- This milestone does not create worktrees or task bundles.
- Retry and stale recovery are separate milestones.

