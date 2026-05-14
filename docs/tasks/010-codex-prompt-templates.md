# Codex Prompt Templates

## Goal

Create prompt templates that define Codex analysis responsibilities, allowed decisions, strict JSON output, and the private-repo security boundary.

## Implementation Scope

- Create prompt files for `0.15` PR analysis, master PR analysis, test transplantation, and fix verification.
- Move task-builder analysis instructions to repository prompt templates.
- Select the `0.15` analysis prompt for PRs merged into upstream `0.15`.
- Select the master analysis prompt for PRs merged into upstream `master`.
- Keep test transplantation and fix verification prompts available for later milestones.
- Require strict JSON output and the configured `output/codex_result.json` path.
- Specify the JSON field shapes expected by later result schema and validator tasks.
- Require the master PR analysis prompt to follow an ordered investigation sequence before deciding applicability.
- Repeat the private-repo security boundary in every prompt.

## Expected Behavior

- Prompts forbid private fork access.
- Prompts require strict JSON output.
- Prompts define structured JSON fields, allowed nulls, relative path rules, and decision-specific evidence expectations.
- Prompts define allowed decision values.
- The master PR prompt requires step-by-step investigation before writing a decision.
- Prompts direct uncertain cases to `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`, not silent discard.

## Affected Modules or Commands

- `prompts/analyze_015_pr.md`
- `prompts/analyze_master_pr.md`
- `prompts/transplant_test.md`
- `prompts/verify_fix.md`
- Task builder prompt selection

## Test Plan

- Verify all prompt files exist.
- Verify every prompt includes the private-repo security boundary.
- Verify every prompt requires strict JSON output and references `output/codex_result.json`.
- Verify every prompt defines the structured JSON contract details needed by later validation.
- Verify the master PR prompt includes the required investigation sequence.
- Verify analysis prompts list all allowed decision values.
- Verify uncertain cases are directed to `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.
- Verify task builder selects the branch-specific analysis prompt.

## Assumptions and Explicit Non-goals

- Prompt templates do not validate results; validation belongs to later milestones.
- This milestone specifies the JSON contract in prompt text but does not implement the Python result schema or validator.
- This milestone does not invoke Codex.
- This milestone does not add the result schema model.
- This milestone does not mutate SQLite or queue state.
