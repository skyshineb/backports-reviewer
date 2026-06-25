# v0.2 CLI Automation and Terminal Reporting

## Goal

Add v0.2 foreground CLI automation for bounded sequential analysis batches and
SQLite-backed terminal report views.

The workflow remains:

```text
scan -> list saved PRs -> inspect selected PRs -> analyze bounded batch -> report
```

Scanning must not invoke Codex automatically, and reporting must continue to be
regenerable from SQLite.

## Implementation Scope

- Extend `backport-harness analyze --limit N` so it processes up to `N` queued
  PRs sequentially in queue priority order.
- Keep `analyze --dry-run --limit N` as preview-only.
- Keep `analyze --pr N` as the explicit single-PR path.
- Add batch options:
  - `--max-runtime-minutes FLOAT`, which stops before starting the next PR once
    elapsed time is over the cap.
  - `--fail-fast`, which stops after the first PR-level failure.
- Continue by default after PR-level failures.
- Select a candidate snapshot once at batch command start and do not reselect a
  retryable PR within the same command.
- Preserve existing per-PR atomic state transitions and Codex result validation.
- Handle `Ctrl-C` as a graceful stop request between PRs where possible.
- Print a Rich terminal batch summary with processed PRs, final queue statuses,
  failures, skipped items, elapsed time, and stop reason.
- Extend `backport-harness report` with terminal views:
  - `report --view summary`
  - `report --view candidates`
  - `report --view inconclusive`
  - `report --view discarded`
  - `report --view audit`
- Add report view filters:
  - `--limit`
  - `--decision`
  - `--queue-status`
  - `--review-status`
  - `--details`
- Add `--no-files` for `report --view ...` so terminal output can be printed
  from SQLite without rewriting report files.
- Refactor report categorization enough for file reports and terminal views to
  share the same decision groups.
- Update `README.md` and `docs/usage.md` with the v0.2 batch and terminal-report
  workflow.

## Expected Behavior

- `backport-harness analyze --limit 5` analyzes up to five queued PRs in the
  same order as the dry-run preview.
- `backport-harness analyze --dry-run --limit 5` prints only the selected PRs and
  does not create task bundles, invoke Codex, or mutate queue state.
- `backport-harness analyze --pr 12345` remains a single-PR command.
- `--max-runtime-minutes` never terminates an in-flight Codex process; it only
  prevents the next PR from starting once the cap has been reached.
- Without `--fail-fast`, a failed PR does not prevent later selected PRs from
  running in the same command.
- With `--fail-fast`, the batch stops after the first PR-level failure.
- Retryable failures produced during a batch are not selected again by that same
  command.
- Terminal batch summary clearly reports completed work, failures, skipped PRs,
  elapsed time, and why the batch stopped.
- Terminal report views read from SQLite and can be printed without writing
  report files when `--no-files` is used.
- Existing report files remain `backport-candidates.md`, `inconclusive.md`,
  `discarded.jsonl`, and `full-audit.jsonl`, with unchanged file formats.

## Affected Modules or Commands

- `backport_harness/commands/analyze.py`
- `backport_harness/analysis_runner.py`
- `backport_harness/commands/report.py`
- `backport_harness/report_writer.py`
- `backport_harness/main.py`
- `backport_harness/storage.py`, only if additional read helpers are needed
- Command: `backport-harness analyze`
- Command: `backport-harness report`
- `README.md`
- `docs/usage.md`

## Test Plan

- Add unit tests for batch ordering, limit handling, runtime cap,
  continue-on-error behavior, `--fail-fast`, and same-command non-reselection of
  retryable failures.
- Add CLI tests for:
  - `analyze --limit`
  - `analyze --dry-run --limit`
  - invalid analyze option combinations
  - batch terminal summary output
- Add report-view tests using recorded Rich console output for:
  - summary
  - filters
  - details mode
  - `--no-files`
- Run focused tests for analysis runner, CLI, report writer, storage, and command
  modules affected by usage changes.
- Run full `.venv/bin/python -m pytest`.

## Assumptions and Explicit Non-goals

- "Automatic" means one foreground CLI command processes a bounded batch from the
  already-scanned queue.
- Batch mode remains sequential because Codex runs are expensive and current
  queue locking is per PR.
- `--max-runtime-minutes` uses elapsed wall-clock time at PR boundaries and does
  not replace per-PR `codex.timeout_seconds`.
- Terminal views are the only new report output surface in v0.2.
- Do not add a daemon.
- Do not run Codex in parallel.
- Do not add CSV or HTML exports.
- Do not access private forks, private patches, private repository history, or
  private test results.
- Do not change the SQLite schema unless implementation proves it unavoidable.
