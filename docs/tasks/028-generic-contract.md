# Generic Harness Contract

## Goal

Make the harness public contract generic by replacing remaining Hudi-era
`master` / `0.15` / `015` result, schema, report, prompt, and documentation
names with source-branch and target-ref terminology.

## Implementation Scope

- Rename Codex result decisions to generic source/target names:
  - `DIRECT_015_BUGFIX` -> `TARGET_BRANCH_BUGFIX`
  - `MASTER_NOT_APPLICABLE` -> `SOURCE_NOT_APPLICABLE`
  - `MASTER_POSSIBLY_APPLICABLE` -> `SOURCE_POSSIBLY_APPLICABLE`
  - `MASTER_REPRODUCED_ON_015` -> `SOURCE_REPRODUCED_ON_TARGET`
  - `MASTER_FIX_VERIFIED_ON_015` -> `SOURCE_FIX_VERIFIED_ON_TARGET`
- Rename result JSON fields:
  - `target_branch` -> `upstream_branch`
  - `applicability.applies_to_oss_015` ->
    `applicability.applies_to_target_ref`
  - `production_files_relevant_to_015` ->
    `production_files_relevant_to_target`
- Bump Codex result JSON to `schema_version: 2`.
- Rename SQLite columns and stored values through a packaged migration.
- Update prompt templates, prompt selection, validation, storage, inspect,
  reports, and tests to use generic names.
- Make Lance the default `config.yaml` and move the former Hudi default to
  `config.hudi.yaml`.
- Replace old worktree/priority helper names where they leak into the public
  implementation surface.
- Update README, usage, design, and implementation-step docs for the generic
  contract.

## Expected Behavior

- New analysis task bundles instruct Codex to emit schema version 2 with generic
  decision and field names.
- Existing SQLite databases migrate stored old decision strings and renamed
  columns without losing analysis history.
- Reports and inspect output expose generic names and labels.
- Lance is the default runnable config.
- Hudi remains available through `config.hudi.yaml`.
- The private-fork security boundary remains unchanged.

## Affected Modules or Commands

- `backport_harness/codex_result.py`
- `backport_harness/result_validator.py`
- `backport_harness/storage.py`
- `backport_harness/report_writer.py`
- `backport_harness/prompt_templates.py`
- `backport_harness/state_machine.py`
- `backport_harness/worktree_manager.py`
- `backport_harness/repo_manager.py`
- `backport_harness/task_builder.py`
- `backport_harness/migrations/003_generic_contract.sql`
- `prompts/*.md`
- `config.yaml`
- `config.hudi.yaml`
- `README.md`
- `docs/usage.md`
- `docs/backport_harness_design.md`
- `docs/backport_harness_implementation_steps.md`
- focused tests for config, schema parsing, validation, storage migration,
  reports, prompts, task building, worktrees, state machine, and CLI output

## Test Plan

- Compare this task against:
  - `docs/backport_harness_design.md`
  - `docs/backport_harness_implementation_steps.md`
  - relevant existing task files in `docs/tasks/`
- Run focused tests:
  - `.venv/bin/python -m pytest tests/test_config.py`
  - `.venv/bin/python -m pytest tests/test_codex_result.py`
  - `.venv/bin/python -m pytest tests/test_result_validator.py`
  - `.venv/bin/python -m pytest tests/test_storage.py`
  - `.venv/bin/python -m pytest tests/test_report_writer.py`
  - `.venv/bin/python -m pytest tests/test_prompt_templates.py`
  - `.venv/bin/python -m pytest tests/test_task_builder.py`
  - `.venv/bin/python -m pytest tests/test_worktree_manager.py`
  - `.venv/bin/python -m pytest tests/test_state_machine.py`
  - `.venv/bin/python -m pytest tests/test_cli.py`
- Run full test suite:
  - `.venv/bin/python -m pytest`
- Run safe CLI checks:
  - `.venv/bin/backport-harness --config config.yaml analyze --dry-run --limit 1`
  - `.venv/bin/backport-harness --config config.hudi.yaml analyze --dry-run --limit 1`

## Assumptions and Explicit Non-goals

- This is a breaking contract change for new Codex result JSON.
- Existing SQLite analysis history is preserved through migration, not
  discarded.
- Existing task output JSON files under `workspace/` are not rewritten; SQLite
  remains the source of truth for reports and inspection.
- Historical task journals may mention old names as historical record.
- This task does not continue Lance PR analysis.
- This task does not access private forks, private patches, private history, or
  private test results.
