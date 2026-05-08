# Fix Verification Support

## Goal

Support Codex-driven adapted fix verification on public OSS `0.15` and store high-confidence evidence.

## Implementation Scope

TBD from design docs before implementation. This milestone should validate adapted patches, after-fix test logs, and upgraded decisions.

## Expected Behavior

- Test fails before fix.
- Adapted fix is applied in the public worktree.
- Test passes after fix.
- Patch and logs are saved.
- Report can show `MASTER_FIX_VERIFIED_ON_015` with high confidence.

## Affected Modules or Commands

- Prompt templates
- Codex result schema
- Result validator
- Decision/test storage
- Report writer

## Test Plan

TBD. At minimum, cover valid verified fix, missing patch, missing after-fix log, passing test without before-fix failure, and failed after-fix test.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- This milestone never applies fixes to the private fork.

