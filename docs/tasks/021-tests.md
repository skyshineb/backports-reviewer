# Tests

## Goal

Build a reliable test suite for harness behavior without requiring real GitHub access, real Codex execution, or private repository data.

## Implementation Scope

- Use `pytest`.
- Add focused tests for config, security, Codex runner, worktree manager, task builder, and analysis flow as the corresponding milestones are implemented.
- Mock `subprocess.Popen` for Codex runner tests.
- Mock `subprocess.run` for Git worktree tests.
- Use temp directories for repo, worktree, task, and path validation.
- Use temp SQLite DBs for analysis state tests.
- Use fake GitHub client objects for scanner and task-builder tests.
- Assert subprocess argv and env directly.
- Assert GitHub token variables are stripped while normal environment values remain.

## Expected Behavior

- CI can run tests without real Codex.
- CI can run tests without a GitHub token.
- Critical state transitions are covered.
- Security-sensitive subprocess/env behavior is tested directly.

## Affected Modules or Commands

- `tests/fakes.py`
- `tests/test_config.py`
- `tests/test_security.py`
- `tests/test_codex_runner.py`
- `tests/test_worktree_manager.py`
- `tests/test_task_builder.py`
- `tests/test_analysis_flow.py`
- Other focused tests introduced by milestone work

## Test Plan

- Config tests cover valid YAML, defaults, env-token loading, embedded-token rejection, and forbidden path overlap.
- Codex runner tests cover argv, logs, JSONL session ID parsing, timeout process-group kill, and credential stripping.
- Worktree tests cover clone, fetch, detached worktree creation, safe stale replacement, and forbidden path rejection.
- Task builder tests cover expected files, output dirs, branch-specific instructions, and no private path strings.
- Analysis-flow tests cover `TASK_PREPARED -> CODEX_RUNNING -> CODEX_DONE`, timeout to `NEEDS_RETRY`, non-zero exit log preservation, malformed result retry, and successful reportable result.

## Assumptions and Explicit Non-goals

- Tests should be added with the milestone that introduces behavior.
- This task coordinates test coverage expectations; it does not require all tests before the corresponding implementation exists.

