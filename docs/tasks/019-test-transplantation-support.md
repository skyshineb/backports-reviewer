# Test Transplantation Support

## Goal

Support Codex-driven regression test transplantation into public OSS `0.15` and store before-fix test results.

## Implementation Scope

- Expand prompt guidance for Codex-driven regression test transplantation in public OSS `0.15`.
- Keep `schema_version: 1` and the existing result fields:
  - `test_transplant`
  - `test_before_fix`
  - `fix_verification`
- Harden result validation for transplant-related outcomes.
- Store validated before-fix test attempts in `test_runs`, including inconclusive attempts.
- Add focused tests for transplant outcome mapping, validation, and storage.

## Expected Behavior

- Codex can attempt to transplant or adapt a focused regression test.
- Harness stores command, exit code, result, and log path.
- A successful before-fix reproduction becomes `MASTER_REPRODUCED_ON_015`.
- If a transplanted test passes before the fix, the PR remains `MASTER_POSSIBLY_APPLICABLE` when positive code evidence exists.
- Failed, flaky, non-applicable, or non-compiling transplant attempts become `INCONCLUSIVE`, not discarded.
- Missing public regression tests do not cause discard by themselves.

## Affected Modules or Commands

- Prompt templates
- Codex result schema
- Result validator
- Test-run storage
- Analysis flow

## Test Plan

- Cover prompt guidance for test not found, not applicable, does not compile, expected failure, unrelated failure, passed, and flaky outcomes.
- Cover result schema parsing for supported transplant and before-fix result values.
- Cover result validation for:
  - `MASTER_REPRODUCED_ON_015` with expected before-fix failure.
  - invalid reproduced claims without expected-failure proof.
  - `MASTER_POSSIBLY_APPLICABLE` with passing before-fix test and code evidence.
  - `INCONCLUSIVE` for not found, not applicable, does not compile, unrelated failure, and flaky outcomes.
- Cover storage of before-fix test attempts for non-verified decisions.
- Run `pytest tests/test_prompt_templates.py`.
- Run `pytest tests/test_codex_result.py`.
- Run `pytest tests/test_result_validator.py`.
- Run `pytest tests/test_storage.py tests/test_analysis_runner.py`.
- Run full `pytest`.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, tasks 012, 013, 014, and 024.
- No SQLite migration is needed because `test_runs` already stores phase, command, exit code, result, and log path.
- No new CLI command is needed; transplantation remains part of Codex analysis.
- Do not change the Codex result schema version.
- Do not implement fix verification in this milestone; that remains task 020.
- Do not access private forks, private patches, private repository history, private test results, or private paths.
