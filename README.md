# Backports Reviewer

`backports-reviewer` is a Python harness for building a public-OSS backport review queue. The harness is intentionally split into small implementation milestones under `docs/tasks/`.

## Current Implementation Status

The current implementation covers milestones 001 through 005:

- Python package metadata
- `backport-harness` CLI entry point
- basic logging setup
- SQLite database initialization and idempotent migrations
- typed YAML config loading with required-field validation
- documented config defaults, including Codex and stale-run timeouts
- GitHub token lookup from the configured environment variable
- relative path normalization for configured workspace paths
- forbidden private path prefix checks
- slow, polite GitHub scanning for public upstream merged PRs
- SQLite storage for PR metadata, changed files, scan audit rows, and analysis queue rows
- saved PR listing with branch, queue status, date, limit, and ordering filters
- detailed saved PR inspection with changed files, queue state, decisions, evidence, logs, tests, and review status
- dry-run analysis candidate selection by queue priority
- public upstream clone and OSS `0.15` worktree preparation
- focused CLI, storage, and config tests

It does not yet implement Codex execution, task bundles, reports, retry commands, or human review commands.

## Linux Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
```

## Usage

All commands accept `--config config.yaml`; it defaults to `config.yaml`.

### General

```sh
.venv/bin/backport-harness --help
.venv/bin/backport-harness version
.venv/bin/backport-harness --config config.yaml version
```

- `--help` shows global options and available commands.
- `version` prints the installed package version.

### Database

```sh
.venv/bin/backport-harness --config config.yaml db init
```

- `db init` creates or migrates the configured SQLite database.
- The default project config writes to `workspace/backport_harness.sqlite3`.
- The command is idempotent and safe to run more than once.

### Scan GitHub PRs

```sh
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch master
```

- `scan` reads public upstream GitHub PRs merged in the requested `merged_at` date range.
- If `--branch` is omitted, every branch listed in `github.branches` is scanned.
- Saved PRs are upserted, changed files are refreshed, queue rows are created if missing, and scan runs are audited.
- Scanning does not invoke Codex or create local worktrees.

Optional GitHub authentication is read from the environment variable named by `github.token_env`, usually:

```sh
export GITHUB_TOKEN=...
```

### List Saved PRs

```sh
.venv/bin/backport-harness --config config.yaml list-prs
.venv/bin/backport-harness --config config.yaml list-prs --branch master
.venv/bin/backport-harness --config config.yaml list-prs --status QUEUED_FOR_ANALYSIS
.venv/bin/backport-harness --config config.yaml list-prs --from-date 2024-01-01 --to-date 2024-01-31 --limit 50
.venv/bin/backport-harness --config config.yaml list-prs --order-by priority
```

- `list-prs` reads only the local SQLite database.
- It shows PR number, branch, merged date, queue status, priority, latest decision, and title.
- Supported `--order-by` values are `merged-at`, `branch`, `priority`, and `status`.
- It does not scan GitHub, invoke Codex, or modify queue state.

### Inspect One Saved PR

```sh
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
```

- `inspect` reads one saved PR from the local SQLite database.
- It shows PR metadata, changed files, queue state, latest decision, evidence, analysis log paths, test runs, and human review status when present.
- It does not scan GitHub, invoke Codex, or modify queue state.

### Plan Analysis Candidates

```sh
.venv/bin/backport-harness --config config.yaml analyze --dry-run
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 10
```

- `analyze --dry-run` selects queued PRs by priority and merge date.
- It shows the PRs that would be analyzed later, without invoking Codex.
- Running `analyze` without `--dry-run` currently fails because Codex execution is not implemented yet.

### Prepare Public OSS Worktree

```sh
.venv/bin/backport-harness --config config.yaml prepare --pr 12345
```

- `prepare` clones the configured public upstream repository if needed.
- It fetches configured upstream branches and creates a clean detached `origin/0.15` worktree.
- The default worktree path is `workspace/worktrees/pr-12345-015/`.
- It rejects configured private path overlaps and remote URL mismatches.
- It does not invoke Codex, create task bundles, or modify SQLite.

### Current Workflow

```sh
.venv/bin/backport-harness --config config.yaml db init
.venv/bin/backport-harness --config config.yaml scan --from-date 2024-01-01 --to-date 2024-01-31 --branch master
.venv/bin/backport-harness --config config.yaml list-prs --limit 20
.venv/bin/backport-harness --config config.yaml inspect --pr 12345
.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 5
.venv/bin/backport-harness --config config.yaml prepare --pr 12345
```

## Linux Test Commands

```sh
.venv/bin/pytest
.venv/bin/pytest tests/test_config.py tests/test_cli.py tests/test_storage.py
.venv/bin/pytest tests/test_github_client.py tests/test_scan.py tests/test_cli.py
```
