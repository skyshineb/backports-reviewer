# Documentation

## Goal

Document setup, security boundaries, workflows, and troubleshooting so a new engineer can operate the harness safely.

## Implementation Scope

- Update `README.md` to describe the currently implemented harness behavior and remove stale implementation-status notes.
- Add operator-focused usage documentation under `docs/` for setup, configuration, public-only safety boundaries, GitHub token setup, scanning, listing, inspection, analysis, stale recovery, retry, reports, and human review.
- Keep documented command names and options aligned with the implemented Typer CLI.
- Document the intended public-OSS workflow:

  ```text
  db init -> scan -> list-prs -> inspect -> analyze --dry-run -> analyze --pr -> recover/retry as needed -> report -> review
  ```

- Document that reports are generated from SQLite and can be regenerated without invoking Codex.
- Document that retry-by-status is limited to operational queue statuses `NEEDS_RETRY` and `FAILED_INFRA`; retrying an inconclusive decision requires explicit `--pr`.
- Document that `recover-stale` uses the configured stale timeout by default and supports `--older-than-hours`.

## Expected Behavior

- A new engineer can set up the tool.
- A new engineer can configure only public upstream paths and understand why private fork paths are forbidden.
- A new engineer can run scanner, listing, and inspection workflows.
- A new engineer can prepare a public worktree or task bundle for one PR.
- A new engineer can analyze one selected PR and understand how Codex output is validated and stored.
- A new engineer can recover stale runs, retry failed work, regenerate reports, and record human review status.
- Documented command examples match implemented CLI names and options.

## Affected Modules or Commands

- `README.md`
- `docs/usage.md`
- Example config or workflow snippets
- Commands documented, but not changed:
  - `backport-harness db init`
  - `backport-harness scan`
  - `backport-harness list-prs`
  - `backport-harness inspect`
  - `backport-harness prepare`
  - `backport-harness prepare-bundle`
  - `backport-harness analyze`
  - `backport-harness recover-stale`
  - `backport-harness retry`
  - `backport-harness report`
  - `backport-harness review`

## Test Plan

- Verify documented commands against the CLI implementation and command help:

  ```sh
  .venv/bin/backport-harness --help
  .venv/bin/backport-harness db --help
  .venv/bin/backport-harness scan --help
  .venv/bin/backport-harness analyze --help
  .venv/bin/backport-harness retry --help
  .venv/bin/backport-harness recover-stale --help
  .venv/bin/backport-harness report --help
  .venv/bin/backport-harness review --help
  ```

- Run the full test suite:

  ```sh
  .venv/bin/pytest
  ```

- Search for stale documentation claims about missing result validation, reports, retry, stale recovery, or human review commands.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, and relevant existing task files through task 021.
- Documentation must reiterate that the harness never accesses private forks, private patches, private history, or private test data.
- This task is documentation-only. It does not change CLI behavior, storage, schemas, prompts, analysis behavior, report output, or tests.
- Do not document private-fork operating procedures beyond the explicit safety boundary and human-review handoff.
