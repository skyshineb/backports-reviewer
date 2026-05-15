# Codex Result Schema

## Goal

Define the strict JSON schema accepted from Codex before any decision can be stored.

## Implementation Scope

- Add `pydantic` as a project dependency.
- Implement `backport_harness/codex_result.py`.
- Define Pydantic models for the `output/codex_result.json` contract specified by the design docs and prompt templates.
- Define enums for:
  - decision
  - confidence
  - test/transplant/fix result claims
  - evidence type
- Provide helpers to parse a JSON string/bytes payload and to load a result from disk.
- Enforce generic schema shape only: required fields, known enum values, non-empty required strings, relative paths, and log/patch path prefixes.

## Expected Behavior

- Valid `output/codex_result.json` parses successfully.
- Malformed JSON or unknown enum values fail validation.
- Required generic fields are enforced.
- `schema_version` must be `1`.
- `target_branch` must be `master` or `0.15`.
- Evidence must be present and use known evidence types.
- Paths in JSON must be relative and must not contain `..` segments.
- Log paths must be under `output/logs/` and patch paths must be under `output/patches/`.

## Affected Modules or Commands

- `pyproject.toml`
- `backport_harness/codex_result.py`
- `tests/test_codex_result.py`

## Test Plan

- Valid representative master result parses successfully.
- Valid representative `0.15` result parses successfully.
- Malformed JSON fails validation.
- Missing required top-level field fails validation.
- Unknown decision fails validation.
- Unknown confidence fails validation.
- Unknown evidence type fails validation.
- Empty required strings fail validation.
- Absolute paths fail validation.
- Paths containing `..` fail validation.
- Log paths outside `output/logs/` fail validation.
- Patch paths outside `output/patches/` fail validation.
- Run `pytest tests/test_codex_result.py`.
- Run full `pytest`.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, and the existing prompt templates.
- Use Pydantic v2 for result models.
- `schema_version` is fixed to `1`.
- `target_branch` is limited to `master` and `0.15`.
- `evidence` must be non-empty.
- Optional design-example fields such as `bugfix_classification`, `touched_components`, `production_files_relevant_to_015`, and `test_files_used` are accepted but not required.
- This milestone validates schema shape only; decision-specific evidence validation is separate.
- Do not validate referenced file existence, patch existence, or test exit-code consistency in this task.
