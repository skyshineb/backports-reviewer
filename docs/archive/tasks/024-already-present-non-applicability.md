# Already-Present Non-Applicability

## Goal

Accept master PRs as not applicable when the public OSS 0.15 worktree already contains the same fix behavior.

## Implementation Scope

- Update the design and implementation documentation for `MASTER_NOT_APPLICABLE`.
- Update analysis prompt templates so Codex may use `MASTER_NOT_APPLICABLE` for already-present public OSS 0.15 fixes.
- Update result validation to treat already-present fix behavior as a strong non-applicability basis.
- Add focused tests for the new accepted basis and keep vague non-applicability reasons invalid.

## Expected Behavior

- `MASTER_NOT_APPLICABLE` remains valid only when `applicability.applies_to_oss_015` is `false` and `non_applicability` evidence is present.
- Validation accepts evidence or applicability text showing that the master fix behavior is already present in public OSS 0.15.
- Validation still rejects unsupported text such as "probably not relevant."
- The Codex result schema shape and schema version remain unchanged.

## Affected Modules or Commands

- `backport_harness/result_validator.py`
- `prompts/analyze_master_pr.md`
- `prompts/analyze_015_pr.md`
- `docs/backport_harness_design.md`
- `docs/backport_harness_implementation_steps.md`
- `tests/test_result_validator.py`
- `tests/test_prompt_templates.py`

## Test Plan

- Run `pytest tests/test_result_validator.py`.
- Run `pytest tests/test_prompt_templates.py`.
- Run `pytest tests/test_analysis_runner.py` if focused validation or prompt tests reveal integration impact.
- Run full `pytest` if focused tests pass.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, task 012, and task 013.
- This task does not add fields, enum values, database migrations, or a schema version bump.
- This task does not manually rewrite existing task output or database rows for PR 10430.
- This task does not access private forks, private patches, private repository history, or private test results.
