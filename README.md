# Backports Reviewer

`backports-reviewer` is a Python harness for building a public-OSS backport review queue. The harness is intentionally split into small implementation milestones under `docs/tasks/`.

Task 001 provides only the project skeleton:

- Python package metadata
- `backport-harness` CLI entry point
- basic logging setup
- placeholder YAML config loading
- focused CLI tests

It does not implement GitHub scanning, SQLite storage, Codex execution, worktrees, reports, retries, or strict config validation.

## Install

```sh
python -m pip install -e ".[test]"
```

## Usage

```sh
backport-harness --help
backport-harness version
backport-harness --config config.yaml version
```

## Test

```sh
pytest
```

