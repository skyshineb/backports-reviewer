# Test Transplantation Support

## Goal

Support Codex-driven regression test transplantation into public OSS `0.15` and store before-fix test results.

## Implementation Scope

TBD from design docs before implementation. This milestone should expand prompts, result validation, and storage around transplanted test attempts.

## Expected Behavior

- Codex can attempt to transplant or adapt a focused regression test.
- Harness stores command, exit code, result, and log path.
- Failed transplant becomes `INCONCLUSIVE`, not discarded.

## Affected Modules or Commands

- Prompt templates
- Codex result schema
- Result validator
- Test-run storage
- Analysis flow

## Test Plan

TBD. At minimum, cover test not found, not applicable, does not compile, expected failure, unrelated failure, passed, and flaky outcomes.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- This is post-MVP reliability work.

