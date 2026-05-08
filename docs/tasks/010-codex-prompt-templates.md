# Codex Prompt Templates

## Goal

Create prompt templates that define Codex analysis responsibilities, allowed decisions, strict JSON output, and the private-repo security boundary.

## Implementation Scope

TBD from design docs before implementation. This milestone should create prompt files for `0.15` PR analysis, master PR analysis, test transplantation, and fix verification.

## Expected Behavior

- Prompts forbid private fork access.
- Prompts require strict JSON output.
- Prompts define allowed decision values.
- Prompts direct uncertain cases to `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`, not silent discard.

## Affected Modules or Commands

- `prompts/analyze_015_pr.md`
- `prompts/analyze_master_pr.md`
- `prompts/transplant_test.md`
- `prompts/verify_fix.md`
- Task builder prompt selection

## Test Plan

TBD. At minimum, static tests should verify prompt files exist, include the security boundary, mention strict JSON output, and list allowed decision values.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- Prompt templates do not validate results; validation belongs to later milestones.

