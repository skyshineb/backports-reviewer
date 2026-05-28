# Align Infra Result Values

## Goal

Prevent Codex from writing ad hoc result enum values when a focused test or fix
verification command cannot run because local infrastructure is unavailable.

## Implementation Scope

- Update prompt templates to list the exact allowed result enum values for
  `test_transplant.result`, `test_before_fix.result`, and
  `fix_verification.result`.
- Clarify that unavailable local tooling, such as missing Maven, must be recorded
  with `infra_failure` evidence and an accepted result value.
- Keep the Python schema strict; do not accept arbitrary infrastructure-specific
  strings such as `failed_to_start_maven_unavailable`.
- Add tests that protect the prompt/schema alignment.

## Expected Behavior

- Codex output remains valid JSON schema even when a command cannot start.
- Missing Maven or similar unavailable tooling is represented as infrastructure
  evidence plus an allowed result value, not a custom enum string.
- Invalid custom enum strings remain rejected by the validator.

## Affected Modules or Commands

- `prompts/analyze_master_pr.md`
- `prompts/analyze_015_pr.md`
- `prompts/transplant_test.md`
- `prompts/verify_fix.md`
- Prompt/schema tests

## Test Plan

- Run focused prompt and result-schema tests.
- Run the full test suite.

## Assumptions and Explicit Non-goals

- This task does not change decision semantics or queue transitions.
- This task does not add a new schema enum value for every possible missing tool.
- This task does not rerun the full real PR e2e; a later manual retry can verify
  the updated prompt behavior against live Codex.
