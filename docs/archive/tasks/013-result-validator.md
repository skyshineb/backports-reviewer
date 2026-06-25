# Result Validator

## Goal

Validate Codex claims against schema, decision-specific evidence requirements, logs, patches, and test exit codes before storing decisions.

## Implementation Scope

- Implement `backport_harness/result_validator.py`.
- Validate that `output/codex_result.json` exists and parses through the strict Codex result schema.
- Validate referenced log files under the task bundle's `output/logs/`.
- Validate referenced patch files under the task bundle's `output/patches/` when required by the decision.
- Validate decision-specific evidence and test exit-code claims for:
  - `MASTER_FIX_VERIFIED_ON_015`
  - `MASTER_REPRODUCED_ON_015`
  - `MASTER_NOT_APPLICABLE`
  - `INCONCLUSIVE`
  - `NEEDS_HUMAN_REVIEW`
  - `FAILED_INFRA`
- Integrate validation after a successful Codex process exit.
- Mark valid results as ready for decision storage without storing decisions in this milestone.
- Mark invalid results retryable or infra-failed according to remaining attempts.

## Expected Behavior

- Invalid Codex claims are rejected.
- Invalid results mark PRs retryable or infra-failed according to failure type.
- Valid results can proceed to decision storage.
- A valid `FAILED_INFRA` Codex decision is accepted only when supported by infra-failure evidence.
- Missing, malformed, or evidence-invalid result files do not create decision, evidence, or test-run rows.

## Affected Modules or Commands

- `backport_harness/result_validator.py`
- Result schema models
- Analysis integration
- Queue state transitions
- Storage helpers for validation state only

## Test Plan

- Cover a valid `MASTER_FIX_VERIFIED_ON_015` result.
- Cover missing result file and malformed/schema-invalid JSON.
- Cover missing referenced log files.
- Cover missing required patch files.
- Cover fix-verified claims with invalid before-fix or after-fix exit codes.
- Cover valid and invalid `MASTER_REPRODUCED_ON_015`.
- Cover valid and invalid `MASTER_NOT_APPLICABLE`.
- Cover valid and invalid `INCONCLUSIVE`.
- Cover valid and invalid `FAILED_INFRA`.
- Cover analysis integration for valid result, invalid retryable result, and invalid max-attempts result.
- Run `pytest tests/test_result_validator.py`.
- Run relevant integration tests for analysis, storage, and queue state.
- Run full `pytest`.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, task 012, and task 014.
- Codex output is never trusted without Python validation.
- Task 014 remains responsible for inserting validated decisions into `decisions`, `evidence`, and `test_runs`.
- This task may update `analysis_runs` and `analysis_queue` to represent validation success or validation failure.
- Validator checks only task-bundle files and never accesses private forks, private patches, private repository history, or private test results.
