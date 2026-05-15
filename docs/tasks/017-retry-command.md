# Retry Command

## Goal

Allow selected operational retry PRs to be queued for another analysis attempt while preserving prior analysis history.

## Implementation Scope

Implement `backport-harness retry` selection by queue status or PR number.

Supported commands:

```sh
backport-harness retry --status NEEDS_RETRY --limit 3
backport-harness retry --status FAILED_INFRA --limit 3
backport-harness retry --pr 12345
```

For task 017, bulk retry by `--status` is intentionally limited to operational queue statuses:

- `NEEDS_RETRY`
- `FAILED_INFRA`

Bulk `--status INCONCLUSIVE` is rejected. This is an intentional deviation from the broader design-doc example because `INCONCLUSIVE` is a decision status for human review, not an operational queue state. An inconclusive PR may be retried only when selected explicitly with `--pr`.

Retrying resets selected queue rows to `QUEUED_FOR_ANALYSIS`, clears `locked_at`, `locked_by`, `last_error`, and `next_retry_at`, and updates `updated_at`.

Retrying must not increment `analysis_queue.attempts`. Attempts increment only when a new analysis run starts.

## Expected Behavior

- `--status NEEDS_RETRY` retries matching queue rows up to the selected limit.
- `--status FAILED_INFRA` retries matching queue rows up to the selected limit.
- `--status INCONCLUSIVE` is rejected with a clear message.
- `--pr 12345` retries one saved PR when it is not `CODEX_RUNNING`, attempts are below `config.codex.max_attempts_per_pr`, and either:
  - the queue status is `NEEDS_RETRY`;
  - the queue status is `FAILED_INFRA`; or
  - the latest stored decision is `INCONCLUSIVE`.
- Invalid selector combinations are rejected:
  - exactly one selector is required: `--pr` or `--status`;
  - `--limit` cannot be combined with `--pr`;
  - `--pr` and `--limit` must be positive integers when provided.
- Rows at or above `config.codex.max_attempts_per_pr` are skipped.
- `CODEX_RUNNING` rows are not retried.
- Previous `analysis_runs`, `decisions`, `evidence`, `test_runs`, task directories, logs, and patches remain untouched.

## Affected Modules or Commands

- `backport_harness/commands/retry.py`
- `backport_harness/storage.py`
- `backport_harness/main.py`
- Command: `backport-harness retry`
- Tests in `tests/test_storage.py` and `tests/test_cli.py`

## Test Plan

Storage tests:

- Retry by `NEEDS_RETRY`.
- Retry by `FAILED_INFRA`.
- Explicit PR retry for latest `INCONCLUSIVE`.
- Bulk `INCONCLUSIVE` rejected.
- Max-attempt rows skipped.
- Running rows not retried.
- Attempts unchanged.
- Prior runs, decisions, evidence, and test runs preserved.

CLI tests:

- `retry --status NEEDS_RETRY --limit 3`.
- `retry --status FAILED_INFRA --limit 3`.
- `retry --pr 12345`.
- Invalid selector combinations.
- Invalid PR and limit values.
- `retry --status INCONCLUSIVE` rejection message.
- Missing database reports zero retries cleanly.

Run:

```sh
pytest tests/test_storage.py
pytest tests/test_cli.py
pytest
```

## Assumptions and Explicit Non-goals

- `INCONCLUSIVE` remains a reportable human-review decision, not an operational retry state.
- Explicit PR retry is the deliberate override for reanalyzing an inconclusive result.
- Attempts increment when a new analysis starts, not when retry is queued.
- This milestone does not invoke Codex, rebuild task bundles, remove task directories, delete logs, or rewrite prior analysis records.
