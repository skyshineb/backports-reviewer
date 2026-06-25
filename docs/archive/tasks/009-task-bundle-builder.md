# Task Bundle Builder

## Goal

Build per-PR task bundles that contain only public context needed for Codex analysis.

## Implementation Scope

- Create `backport_harness/task_builder.py`.
- Generate task directories under `workspace/tasks/pr-<number>/`.
- Write `pr.json`, `files_changed.json`, `pr.diff`, and `instructions.md`.
- Pre-create `output/`, `output/logs/`, and `output/patches/`.
- Generate different instruction content for PRs merged to `master` and PRs merged to `0.15`.
- Ensure instructions and bundle files do not contain private paths, private repo names, private patches, or private test data.
- Keep Codex output path aligned with `output/codex_result.json`.

## Expected Behavior

- Task bundle contains public PR metadata, changed files, diff, instructions, and output directories.
- Instructions clearly state the security boundary.
- Bundle creation is deterministic and safe to rerun for the same PR.

## Affected Modules or Commands

- `backport_harness/task_builder.py`
- Optional prepare/analyze integration points
- Tests: `tests/test_task_builder.py`

## Test Plan

- Build a task bundle using fake PR data and temp directories.
- Verify expected files and directories exist.
- Verify branch-specific instructions are selected.
- Verify generated text excludes configured private path strings.
- Verify output/log/patch directories are created.

## Assumptions and Explicit Non-goals

- The task bundle is the only context Codex should need.
- If symlinking/copying the worktree complicates cleanup, store the public worktree path in instructions and run Codex from the worktree.
- This milestone does not invoke Codex.

