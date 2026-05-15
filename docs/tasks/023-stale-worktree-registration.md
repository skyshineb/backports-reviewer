# Stale Worktree Registration Recovery

## Goal

Make repeated `prepare` and `prepare-bundle` runs recover from Git worktree registrations whose directories are missing.

## Implementation Scope

- Update public upstream worktree preparation to clean stale Git worktree metadata before creating the per-PR detached worktree.
- Keep stale cleanup limited to the configured public `worktree_dir` and never remove paths overlapping the upstream clone.
- Preserve the existing `workspace/worktrees/pr-<number>-015/` layout.
- Add focused tests for missing-but-registered worktree recovery.

## Expected Behavior

- Running `prepare` followed by `prepare-bundle` for the same PR replaces the prior public worktree cleanly.
- If the target worktree directory is missing but still registered in Git metadata, the harness prunes or removes the stale registration before `git worktree add`.
- Git worktree cleanup remains restricted to safe public paths.

## Affected Modules or Commands

- `backport_harness/worktree_manager.py`
- `tests/test_worktree_manager.py`
- `backport-harness prepare`
- `backport-harness prepare-bundle`

## Test Plan

- Mock Git subprocess calls and verify stale registrations are pruned before detached worktree creation.
- Verify existing stale directories are still removed safely.
- Run `pytest tests/test_worktree_manager.py`.

## Assumptions and Explicit Non-goals

- This task only addresses stale public upstream worktree setup.
- This task does not change Codex analysis, scanning, queue ordering, or report generation.
- This task does not access private forks, private patches, private history, or private test results.
