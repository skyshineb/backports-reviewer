# Backports Reviewer

`backports-reviewer` is a Python harness for building a public-OSS backport review queue. The harness is intentionally split into small implementation milestones under `docs/tasks/`.

## Current Implementation Status

The current implementation covers milestones 001 through 003:

- Python package metadata
- `backport-harness` CLI entry point
- basic logging setup
- SQLite database initialization and idempotent migrations
- typed YAML config loading with required-field validation
- documented config defaults, including Codex and stale-run timeouts
- GitHub token lookup from the configured environment variable
- relative path normalization for configured workspace paths
- forbidden private path prefix checks
- focused CLI, storage, and config tests

It does not yet implement GitHub scanning, saved-PR listing or inspection, Codex execution, worktrees, reports, retries, or human review commands.

## Linux Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
```

## Usage

```sh
.venv/bin/backport-harness --help
.venv/bin/backport-harness version
.venv/bin/backport-harness --config config.yaml version
.venv/bin/backport-harness --config config.yaml db init
```

## Linux Test Commands

```sh
.venv/bin/pytest
.venv/bin/pytest tests/test_config.py tests/test_cli.py tests/test_storage.py
```
