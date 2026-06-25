# Backports Reviewer

`backports-reviewer` is a Python harness for building a public-OSS backport
review queue. It scans public upstream GitHub pull requests, stores review state
in SQLite, prepares public worktrees and Codex task bundles, validates Codex
analysis output, and generates reports for human review.

The harness is intentionally public-only. It must not access or be configured
with private fork paths, private repository URLs, private patches, private
history, private business logic, or private test results.

## What It Does

- Scans public upstream PRs by merged date and branch.
- Stores PR metadata, changed files, queue state, Codex attempts, decisions,
  evidence, test runs, and human review state in SQLite.
- Lets operators list and inspect saved PRs before spending Codex time.
- Prepares a clean public baseline worktree and task bundle for one PR.
- Runs Codex for one selected PR, then validates the structured result before
  storing any decision.
- Recovers stale runs, retries operational failures, and regenerates reports
  from SQLite.

## What It Does Not Do

- It does not access a private fork.
- It does not apply backports to private code.
- It does not push commits or open pull requests.
- It does not treat Codex output as trusted unless the Python harness validates
  the result schema and referenced evidence.
- It does not replace human review.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/backport-harness --config config.yaml db init
```

Optional GitHub authentication is read from the environment variable named by
`github.token_env` in `config.yaml`:

```sh
export GITHUB_TOKEN=...
```

Do not put token values in `config.yaml`.

## Configuration

The default `config.yaml` targets the public Lance repository (`main` as the
source branch and tag `v7.0.0` as the public target ref). `config.hudi.yaml`
keeps the older Apache Hudi `master`/`0.15` example. Adjust either file for the
public repository, branches, and target ref you want to review.

Important sections:

- `github`: public upstream owner, repo, source branches, optional branch-to-Git
  ref mapping, token environment variable, request delays, retry settings, and
  rate-limit handling.
- `local_repo`: public upstream clone location, public worktree directory, and
  required `target_ref` (`label`, Git `ref`, and worktree suffix).
- `codex`: Codex command, timeout, max attempts, and expected result path.
- `analysis`: default dry-run selection limit and stale-run timeout.
- `reports`: output directory for generated reports.
- `storage`: SQLite database path.
- `security`: optional forbidden private path prefixes.

The default workspace is under `workspace/lance-v7/`; reports are written under
`reports/lance-v7/`.

## Workflow

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

The implemented analysis path runs one selected PR at a time with
`analyze --pr`. Use `analyze --dry-run --limit N` to preview which queued PRs
should be analyzed next.

## Commands

Initialize or migrate the SQLite database:

```sh
.venv/bin/backport-harness --config config.yaml db init
```

Scan public upstream PRs merged in an inclusive `merged_at` date range:

```sh
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch master
```

If `--branch` is omitted, every branch listed in `github.branches` is scanned.
Scanning is idempotent, records audit rows, and does not invoke Codex.

List and inspect saved PRs from local SQLite state:

```sh
.venv/bin/backport-harness --config config.yaml list-prs
.venv/bin/backport-harness --config config.yaml list-prs --status QUEUED_FOR_ANALYSIS --limit 50
.venv/bin/backport-harness --config config.yaml list-prs --order-by priority
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
```

Prepare public analysis inputs without invoking Codex:

```sh
.venv/bin/backport-harness --config config.yaml prepare --pr 12345
.venv/bin/backport-harness --config config.yaml prepare-bundle --pr 12345
```

Preview and run analysis:

```sh
.venv/bin/backport-harness --config config.yaml analyze --dry-run
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 5
.venv/bin/backport-harness --config config.yaml analyze --pr 12345
```

`analyze --pr` creates the task bundle, locks the queue row, invokes Codex,
captures stdout and stderr, validates `output/codex_result.json`, stores valid
decisions and evidence, and preserves task output for inspection. Timeouts,
non-zero exits, malformed JSON, and invalid evidence mark the queue retryable
until the configured attempt limit is reached.

Recover stale runs and retry selected failures:

```sh
.venv/bin/backport-harness --config config.yaml recover-stale
.venv/bin/backport-harness --config config.yaml recover-stale --older-than-hours 2
.venv/bin/backport-harness --config config.yaml retry --status NEEDS_RETRY --limit 3
.venv/bin/backport-harness --config config.yaml retry --status FAILED_INFRA --limit 3
.venv/bin/backport-harness --config config.yaml retry --pr 12345
```

Bulk retry supports only operational queue statuses `NEEDS_RETRY` and
`FAILED_INFRA`. Retrying an `INCONCLUSIVE` decision requires selecting the PR
explicitly with `retry --pr`.

Generate reports and record human review state:

```sh
.venv/bin/backport-harness --config config.yaml report
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status accepted_for_backport
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status backported --comment "Applied internally"
```

## Reports

`report` regenerates files from SQLite and does not require live GitHub access
or Codex execution.

Generated report files:

- `backport-candidates.md`
- `inconclusive.md`
- `discarded.jsonl`
- `full-audit.jsonl`

## Troubleshooting

- Empty list output: run `db init` and `scan`, then verify `storage.sqlite_path`.
- GitHub rate limits: set `GITHUB_TOKEN`, keep delays enabled, and rerun the
  scan. Scans are idempotent.
- Stuck `CODEX_RUNNING`: run `recover-stale`, then retry selected PRs.
- Max attempts reached: inspect the PR and logs before deciding whether to
  adjust config or leave the item failed.
- Invalid Codex output: inspect the task output logs and `codex_result.json`;
  invalid claims are rejected by the harness.
- Private path rejection: keep public workspaces and configured paths away from
  private fork directories.

## More Documentation

See `docs/usage.md` for a fuller operator guide and
`docs/backport_harness_design.md` for design intent.

## Development Checks

```sh
.venv/bin/backport-harness --help
.venv/bin/backport-harness analyze --help
.venv/bin/backport-harness retry --help
.venv/bin/backport-harness recover-stale --help
.venv/bin/pytest
```
