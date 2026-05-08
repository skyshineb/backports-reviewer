# Result Validator

## Goal

Validate Codex claims against schema, decision-specific evidence requirements, logs, patches, and test exit codes before storing decisions.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement generic and decision-specific validation for Codex result files.

## Expected Behavior

- Invalid Codex claims are rejected.
- Invalid results mark PRs retryable or infra-failed according to failure type.
- Valid results can proceed to decision storage.

## Affected Modules or Commands

- `backport_harness/result_validator.py`
- Result schema models
- Analysis integration

## Test Plan

TBD. At minimum, cover generic validation plus decision-specific validation for `MASTER_FIX_VERIFIED_ON_015`, `MASTER_REPRODUCED_ON_015`, `MASTER_NOT_APPLICABLE`, and `INCONCLUSIVE`.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- Codex output is never trusted without Python validation.

