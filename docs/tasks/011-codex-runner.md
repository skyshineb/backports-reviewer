# Codex Runner With Two-Hour Timeout

## Goal

Implement a Codex subprocess runner that executes one prepared analysis safely, captures logs, enforces the default timeout, and records run status without exposing GitHub credentials.

## Implementation Scope

- Create `backport_harness/codex_runner.py`.
- Define `CodexRunRequest` with `prompt`, `cwd`, `timeout_seconds`, `output_result_path`, and optional `extra_env`.
- Define `CodexRunResult` with session ID, exit code, timeout flag, stdout/stderr log paths, optional last-message path, start time, and finish time.
- Invoke Codex as `codex exec -C <cwd> --dangerously-bypass-approvals-and-sandbox --json -o <temp-last-message-file> <prompt>`.
- Store stdout and stderr in task output logs, not directly in SQLite.
- Put the Codex `-o` last-message file outside the git worktree while running, then persist it into the task output directory after completion.
- Spawn with `start_new_session=True`.
- On timeout, signal the process group with `SIGTERM`, wait briefly, then use `SIGKILL`.
- Parse Codex session IDs from JSONL with a recursive UUID search.
- Strip GitHub credential environment variables before every Codex spawn while preserving provider auth needed by Codex.
- Set `GIT_TERMINAL_PROMPT=0`.
- Wire one-PR analysis to lock the queue item, create an `analysis_runs` row, mark `CODEX_RUNNING`, invoke the runner outside an open SQLite transaction, store log paths and exit code, and preserve task directories on failure.

## Expected Behavior

- `backport-harness analyze --pr 12345` can invoke Codex for one prepared PR once prerequisite milestones exist.
- Timeout defaults to 7200 seconds.
- Non-zero exits and timeouts preserve logs and mark retryable or infra-failed state according to the state machine.
- Codex never receives GitHub token environment variables.

## Affected Modules or Commands

- `backport_harness/codex_runner.py`
- Analyze command integration
- Queue/storage integration
- Tests: `tests/test_codex_runner.py`

## Test Plan

- Mock `subprocess.Popen`.
- Assert expected Codex argv.
- Assert stdout/stderr logs are written.
- Assert session ID is parsed from JSONL.
- Assert timeout kills the process group.
- Assert GitHub credential variables are stripped and provider auth remains.
- Assert queue/run status updates happen around execution and not inside a long transaction.

## Assumptions and Explicit Non-goals

- Codex is the only supported agent backend in v1.
- Resume support is out of scope unless a later analysis-flow task requires it.
- Codex cwd must be a task directory or public OSS worktree, never the project root or private path.

