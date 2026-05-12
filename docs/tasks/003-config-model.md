# Config Model

## Goal

Implement typed config loading with strict defaults, path normalization, GitHub token handling, and private-path guard configuration.

## Implementation Scope

- Create `backport_harness/config.py`.
- Load from `config.yaml` by default with CLI support for `--config`.
- Model these config sections: `github`, `local_repo`, `codex`, `analysis`, `reports`, `storage`, and optional `security`.
- Apply documented defaults, including `codex.timeout_seconds = 7200` and `analysis.stale_timeout_seconds = 7200`.
- Read the GitHub token only from the environment variable named by `github.token_env`.
- Reject any config that embeds a GitHub token directly in YAML.
- Resolve workspace paths to absolute paths during config load.
- Validate configured repo, worktree, task, report, and storage paths against configured forbidden private prefixes.
- Update `README.md` with current implementation status and Linux test commands.

## Expected Behavior

- Missing required config fields fail fast.
- Defaults are applied where documented.
- GitHub token values are read from environment only.
- Forbidden path overlap fails before any filesystem or subprocess work happens.

## Affected Modules or Commands

- `backport_harness/config.py`
- `README.md`
- CLI config loading path
- Tests: `tests/test_config.py`

## Test Plan

- Load valid YAML.
- Verify defaults for Codex and stale timeouts.
- Verify token is read from the configured env var.
- Verify token-like YAML fields are rejected.
- Verify relative paths are resolved.
- Verify forbidden path overlaps are rejected.
- Verify documented Linux test commands match the current project setup.

## Assumptions and Explicit Non-goals

- Pydantic is preferred if already selected for result schemas; otherwise use dataclasses plus validation.
- This milestone may define security config data, but reusable security helper functions belong to the worktree/Codex-related milestones unless needed here.
- This milestone does not clone repos, create worktrees, scan GitHub, or invoke Codex.
