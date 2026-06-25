# Backport Harness Usage

This guide describes how to operate the harness against public upstream data. It is for engineers who need to build and review a public-OSS backport candidate queue.

## Safety Boundary

The harness may use only public upstream GitHub data, public upstream branches, public PR diffs, local public OSS worktrees, and public test logs generated during analysis.

Do not configure or expose:

- private fork paths
- private fork remotes
- private patches
- private repository history
- private business logic
- private test results
- local directories containing private fork code

The harness produces a candidate queue and public evidence. Human reviewers use that queue to decide what to do elsewhere; the harness itself does not inspect or modify a private fork.

## Setup

Create an environment and install the package:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
```

Initialize the SQLite database:

```sh
.venv/bin/backport-harness --config config.yaml db init
```

The root `config.yaml` is an editable generic template. It stores state under `workspace/default/`, writes reports under `reports/default/`, sets the default Codex and stale-run timeout to 7200 seconds, and runs Codex with `medium` reasoning effort. Concrete examples are available in `examples/config.lance-v7.yaml` and `examples/config.hudi.yaml`.

Release 0.1 treats the SQLite schema as the first public baseline. If `db init`
reports an incompatible schema, point `storage.sqlite_path` at a fresh database
or recreate the file from public source data.

## Configuration

The important config sections are:

- `github`: public upstream owner, repo, branches, optional branch-to-Git ref mapping, token environment variable, delays, retries, and rate-limit behavior.
- `local_repo`: public upstream clone location, public worktree directory, and required public `target_ref` with `label`, Git `ref`, and `worktree_suffix`.
- `codex`: Codex command, execution mode, timeout, max attempts, expected result file, and reasoning effort.
- `analysis`: default batch limit and stale-run timeout.
- `reports`: report output directory.
- `storage`: SQLite path.

GitHub authentication is optional for public data but useful for rate limits. The token is read from the environment variable named by `github.token_env`:

```sh
export GITHUB_TOKEN=...
```

Do not put token values in `config.yaml`.

## Scan Public PRs

Scan PRs by inclusive `merged_at` date range:

```sh
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch main
```

If `--branch` is omitted, every branch listed in `github.branches` is scanned. The scanner is intentionally slow: it delays between requests and pages, respects rate-limit headers, backs off on transient failures, and records scan audit rows.

Scanning stores PR metadata, changed files, and queue rows in SQLite. It does not invoke Codex.

## Review Saved PRs

List saved PRs:

```sh
.venv/bin/backport-harness --config config.yaml list-prs
.venv/bin/backport-harness --config config.yaml list-prs --branch main
.venv/bin/backport-harness --config config.yaml list-prs --status QUEUED_FOR_ANALYSIS
.venv/bin/backport-harness --config config.yaml list-prs --from-date 2024-01-01 --to-date 2024-01-31 --limit 50
.venv/bin/backport-harness --config config.yaml list-prs --order-by priority
```

Supported ordering values are `merged-at`, `branch`, `priority`, and `status`.

Inspect one PR:

```sh
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
```

Inspection reads only SQLite. It can show PR metadata, changed files, queue state, attempts, errors, latest decision, evidence, test runs, log paths, patch paths, and latest human review state.

## Prepare Public Analysis Inputs

Prepare only the configured public target-ref worktree:

```sh
.venv/bin/backport-harness --config config.yaml prepare --pr 12345
```

Prepare the public Codex task bundle without invoking Codex:

```sh
.venv/bin/backport-harness --config config.yaml prepare-bundle --pr 12345
```

Task bundles are created under the configured task directory and include `pr.json`, `files_changed.json`, `pr.diff`, `instructions.md`, a configured public target-ref worktree reference, and output directories for logs and patches.

## Analyze Selected PRs

Preview analysis candidates:

```sh
.venv/bin/backport-harness --config config.yaml analyze --dry-run
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 5
```

Analyze a bounded foreground batch:

```sh
.venv/bin/backport-harness --config config.yaml analyze --limit 5
.venv/bin/backport-harness --config config.yaml analyze --limit 5 --max-runtime-minutes 30
.venv/bin/backport-harness --config config.yaml analyze --limit 5 --fail-fast
```

Analyze one PR:

```sh
.venv/bin/backport-harness --config config.yaml analyze --pr 12345
```

Batch analysis takes a candidate snapshot at command start, then processes up to
the selected limit sequentially in priority order. The same PR is not reselected
within the same command even if it becomes retryable. By default, a PR-level
failure is recorded and the batch continues to the next selected PR. Use
`--fail-fast` to stop after the first PR-level failure.

`--max-runtime-minutes` is checked only before starting the next PR. It never
kills an in-flight Codex run; per-PR timeouts still come from
`codex.timeout_seconds`.

Both batch and one-PR analysis prepare the public task bundle, lock the queue
row, invoke Codex, capture stdout and stderr, validate
`output/codex_result.json` when present, store valid decisions/evidence/test
runs, and update queue state. Failures preserve task directories and logs for
inspection. If interruption leaves a row in `CODEX_RUNNING`, run
`recover-stale` before retrying.

## Recover and Retry

Recover stale Codex runs:

```sh
.venv/bin/backport-harness --config config.yaml recover-stale
.venv/bin/backport-harness --config config.yaml recover-stale --older-than-hours 2
```

Without `--older-than-hours`, the command uses `analysis.stale_timeout_seconds` from config. Stale `CODEX_RUNNING` rows become `NEEDS_RETRY`; logs and task directories are not deleted.

Retry operational failures:

```sh
.venv/bin/backport-harness --config config.yaml retry --status NEEDS_RETRY --limit 3
.venv/bin/backport-harness --config config.yaml retry --status FAILED_INFRA --limit 3
.venv/bin/backport-harness --config config.yaml retry --pr 12345
```

Bulk retry supports only queue statuses `NEEDS_RETRY` and `FAILED_INFRA`. A PR with the latest decision `INCONCLUSIVE` may be retried only by explicit PR number. Retry resets selected queue rows to `QUEUED_FOR_ANALYSIS` and preserves prior analysis history.

## Reports

Generate reports from SQLite:

```sh
.venv/bin/backport-harness --config config.yaml report
.venv/bin/backport-harness --config config.yaml report --view summary
.venv/bin/backport-harness --config config.yaml report --view candidates --details
.venv/bin/backport-harness --config config.yaml report --view inconclusive --queue-status NEEDS_RETRY --no-files
.venv/bin/backport-harness --config config.yaml report --view audit --decision SOURCE_FIX_VERIFIED_ON_TARGET --limit 20 --no-files
```

Reports are written to `reports.output_dir`:

- `backport-candidates.md`
- `inconclusive.md`
- `discarded.jsonl`
- `full-audit.jsonl`

Reports can be regenerated at any time. They do not require live GitHub access or Codex execution.

Terminal views are available with `--view summary`, `--view candidates`,
`--view inconclusive`, `--view discarded`, and `--view audit`. Filters include
`--limit`, `--decision`, `--queue-status`, `--review-status`, and `--details`.
When a view is requested, report files are regenerated first unless `--no-files`
is supplied.

## Human Review State

Record the latest human review status for a saved PR:

```sh
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status accepted_for_backport
.venv/bin/backport-harness --config config.yaml review --pr 12345 --status backported --comment "Applied internally"
```

Allowed statuses are:

- `pending`
- `accepted_for_backport`
- `rejected`
- `already_present`
- `not_needed`
- `backported`
- `failed_to_backport`

Review rows are append-only; the newest row is shown by `inspect` and reports. The command records review state only and does not perform private-fork work.

## Troubleshooting

- Missing config: commands that need configured GitHub, Codex, repo, report, or storage paths require a valid `--config` file.
- Empty listings: run `db init` and `scan` first, then verify the configured SQLite path.
- Unconfigured branch: use a branch listed in `github.branches`.
- GitHub rate limits: set `GITHUB_TOKEN`, keep request/page delays enabled, and rerun the scan. Scans are idempotent.
- Stuck `CODEX_RUNNING`: run `recover-stale`, then retry selected PRs.
- Max attempts reached: inspect the PR, review logs, and decide whether to adjust config or leave the item failed.
- Invalid Codex output: inspect the task output logs and `codex_result.json`; invalid claims are rejected by the Python harness rather than trusted.
- Private path rejection: move public workspaces away from private fork directories and keep private remotes out of config.

## Verification

Useful local checks:

```sh
.venv/bin/backport-harness --help
.venv/bin/backport-harness db --help
.venv/bin/backport-harness scan --help
.venv/bin/backport-harness analyze --help
.venv/bin/backport-harness retry --help
.venv/bin/backport-harness recover-stale --help
.venv/bin/backport-harness report --help
.venv/bin/backport-harness review --help
.venv/bin/pytest
```
