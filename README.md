# Backports Reviewer

`backports-reviewer` is a Python harness for building a public-OSS backport review queue. It scans public upstream GitHub pull requests, stores state in SQLite, prepares public OSS worktrees and Codex task bundles, validates Codex analysis output, and generates reports for human review.

The harness never accesses the private fork. It must not be configured with private fork paths, private repository URLs, private patches, private history, private business logic, or private test results.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/backport-harness --config config.yaml db init
```

Optional GitHub authentication is read from the environment variable named by `github.token_env` in `config.yaml`:

```sh
export GITHUB_TOKEN=...
```

## Current Workflow

All commands accept `--config config.yaml`; it defaults to `config.yaml`.

```sh
.venv/bin/backport-harness --config config.yaml db init
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch master
.venv/bin/backport-harness --config config.yaml list-prs --limit 20
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 5
.venv/bin/backport-harness --config config.yaml analyze --pr 12345
.venv/bin/backport-harness --config config.yaml report
```

Use `prepare --pr 12345` to create only the public OSS `0.15` worktree, or `prepare-bundle --pr 12345` to create the public Codex task bundle without invoking Codex.

## Commands

```sh
.venv/bin/backport-harness --help
.venv/bin/backport-harness version
.venv/bin/backport-harness --config config.yaml db init
```

- `db init` creates or migrates the configured SQLite database.
- The default project config writes to `workspace/backport_harness.sqlite3`.

```sh
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch master
```

- `scan` reads public upstream GitHub PRs merged in the requested `merged_at` date range.
- If `--branch` is omitted, every branch listed in `github.branches` is scanned.
- Saved PRs are upserted, changed files are refreshed, queue rows are created if missing, and scan runs are audited.
- Scanning does not invoke Codex or create local worktrees.

```sh
.venv/bin/backport-harness --config config.yaml list-prs
.venv/bin/backport-harness --config config.yaml list-prs --branch master
.venv/bin/backport-harness --config config.yaml list-prs --status QUEUED_FOR_ANALYSIS
.venv/bin/backport-harness --config config.yaml list-prs --from-date 2024-01-01 --to-date 2024-01-31 --limit 50
.venv/bin/backport-harness --config config.yaml list-prs --order-by priority
```

- `list-prs` reads only local SQLite state.
- Supported `--order-by` values are `merged-at`, `branch`, `priority`, and `status`.

```sh
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 5
.venv/bin/backport-harness --config config.yaml analyze --pr 12345
```

- `inspect` shows saved PR metadata, changed files, queue state, latest decision, evidence, logs, tests, and human review status.
- `analyze --dry-run` selects queued PRs by priority and merge date without invoking Codex.
- `analyze --pr` prepares the public task bundle, invokes Codex once, validates the result when possible, stores decisions/evidence/test runs, and preserves logs.
- Non-zero exits, timeouts, malformed results, and invalid evidence preserve the task directory and mark the queue retryable until the configured attempt limit is reached.

```sh
.venv/bin/backport-harness --config config.yaml recover-stale
.venv/bin/backport-harness --config config.yaml recover-stale --older-than-hours 2
.venv/bin/backport-harness --config config.yaml retry --status NEEDS_RETRY --limit 3
.venv/bin/backport-harness --config config.yaml retry --status FAILED_INFRA --limit 3
.venv/bin/backport-harness --config config.yaml retry --pr 12345
```

- `recover-stale` marks old `CODEX_RUNNING` rows retryable. Without `--older-than-hours`, it uses `analysis.stale_timeout_seconds`.
- Bulk `retry --status` supports only `NEEDS_RETRY` and `FAILED_INFRA`.
- Retry of an `INCONCLUSIVE` decision must be explicit with `retry --pr`.
- Retry preserves prior runs, decisions, evidence, logs, and patches.

```sh
.venv/bin/backport-harness --config config.yaml report
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status accepted_for_backport
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status backported --comment "Applied internally"
```

- `report` regenerates Markdown and JSONL reports from SQLite into `reports.output_dir`.
- `review` records the latest human review status for one saved PR. It records state only; it does not access or modify a private fork.

## More Documentation

See `docs/usage.md` for setup details, configuration notes, the security boundary, full operator workflows, report files, and troubleshooting.

## Tests

```sh
.venv/bin/pytest
.venv/bin/pytest tests/test_config.py tests/test_cli.py tests/test_storage.py
.venv/bin/pytest tests/test_github_client.py tests/test_scan.py tests/test_cli.py
```
