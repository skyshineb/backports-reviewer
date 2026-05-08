# Recover Stale Runs

## Goal

Recover interrupted or abandoned Codex analysis rows by marking stale `CODEX_RUNNING` queue items retryable.

## Implementation Scope

- Implement `backport-harness recover-stale`.
- Find queue items with `CODEX_RUNNING`.
- Use the configured stale timeout, defaulting to 7200 seconds.
- Support `--older-than-hours 2`.
- Mark stale rows as `NEEDS_RETRY`.
- Update `last_error`.
- Preserve `analysis_runs`, task directories, logs, and patches.

## Expected Behavior

- `CODEX_RUNNING` rows older than the threshold become `NEEDS_RETRY`.
- Non-stale running rows are left untouched.
- Recovery does not delete analysis artifacts.

## Affected Modules or Commands

- Recover-stale command module
- Queue/storage helpers
- Config stale timeout
- Command: `backport-harness recover-stale`

## Test Plan

- Verify default 2-hour timeout behavior.
- Verify custom `--older-than-hours`.
- Verify stale rows transition to `NEEDS_RETRY`.
- Verify non-stale rows remain `CODEX_RUNNING`.
- Verify analysis runs and log paths are preserved.

## Assumptions and Explicit Non-goals

- Recovery is explicit CLI behavior, not a daemon.
- This milestone does not start a retry automatically.

