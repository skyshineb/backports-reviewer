# Project Skeleton

## Goal

Create the minimal Python project structure for `backports-reviewer` so later milestones have a stable CLI, package, config-loading entrypoint, logging setup, and test harness to build on.

## Implementation Scope

- Create the Python package skeleton described in `docs/backport_harness_implementation_steps.md`.
- Add project metadata, CLI entry point, basic logging, a config-loading placeholder, and an initial README.
- Keep this milestone limited to scaffolding; do not implement scanner, storage, analysis, Codex execution, worktrees, reports, or retry behavior.

## Expected Behavior

- `backport-harness --help` works.
- `backport-harness version` works.
- Basic logging can be initialized from the CLI.
- A config file path can be accepted, but full typed validation belongs to `003-config-model.md`.

## Affected Modules or Commands

- `pyproject.toml`
- `README.md`
- `config.yaml`
- `backport_harness/__init__.py`
- `backport_harness/main.py`
- `backport_harness/logging_config.py`
- `tests/test_cli.py`
- Commands: `backport-harness --help`, `backport-harness version`

## Test Plan

- Run the CLI help command.
- Run the version command.
- Run focused CLI tests.

## Assumptions and Explicit Non-goals

- Prefer the CLI framework chosen by the implementation docs.
- This milestone does not create the SQLite schema.
- This milestone does not implement strict config validation.
- This milestone does not call GitHub, Git, or Codex.

