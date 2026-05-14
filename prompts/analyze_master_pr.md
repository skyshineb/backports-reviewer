# Analyze Upstream Master PR

## Security Boundary

Use only public upstream data included in the task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If applicability cannot be determined from public upstream context, choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Inputs

- PR metadata: `pr.json`
- Changed files: `files_changed.json`
- Public PR diff: `pr.diff`
- Public OSS 0.15 worktree path supplied by the task builder

## Responsibility

Decide whether this PR merged into upstream `master` is a real bugfix.
If it is a bugfix, decide whether the affected code exists in public OSS `0.15` and whether the fix is applicable to public OSS 0.15.
Do not silently discard uncertain cases.

## Required Investigation Sequence

Follow this sequence before choosing a decision:

1. Read `pr.json` for PR metadata.
2. Inspect `files_changed.json` and `pr.diff`.
3. Classify the PR type.
4. If the PR is non-bugfix, docs-only, CI-only, or release-only, choose the matching discard decision.
5. Inspect production code changes for bugfix behavior.
6. Check whether each affected module, file, class, or method exists in the public OSS 0.15 worktree.
7. Compare the master logic with the public OSS 0.15 logic.
8. Decide whether to discard, mark possibly applicable, reproduce with a test, or verify an adapted fix.
9. If a usable public regression test exists, try the smallest focused test transplant.
10. If reproduction succeeds, optionally apply or adapt the public fix and verify with the focused test.
11. Write strict JSON to `output/codex_result.json`.

## Allowed Decisions

- `MASTER_NOT_APPLICABLE`
- `MASTER_POSSIBLY_APPLICABLE`
- `MASTER_REPRODUCED_ON_015`
- `MASTER_FIX_VERIFIED_ON_015`
- `INCONCLUSIVE`
- `NEEDS_HUMAN_REVIEW`
- `DISCARDED_NON_BUGFIX`
- `DISCARDED_DOCS_ONLY`
- `DISCARDED_CI_ONLY`
- `DISCARDED_RELEASE_ONLY`
- `FAILED_INFRA`

## FAILED_INFRA Policy

Use `FAILED_INFRA` only for one of these infrastructure failures:

- command timeout
- dependency resolution failure
- filesystem error
- unavailable test infrastructure
- unreadable required input files

Logical uncertainty, missing proof, ambiguous applicability, unsupported adaptation, or inability to reason from public code must use `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`, not `FAILED_INFRA`.

## Strict JSON Output

Write strict JSON only to `output/codex_result.json`.
Use `schema_version: 1`.
Use only the allowed decision values listed above.

The JSON object must include these top-level fields:

- `schema_version`
- `pr_number`
- `target_branch`
- `decision`
- `confidence`
- `summary`
- `human_action`
- `evidence`
- `applicability`
- `test_transplant`
- `test_before_fix`
- `fix_verification`

`confidence` must be one of:

- `very_high`: test fails before fix and passes after adapted fix.
- `high`: regression test reproduces the bug on OSS 0.15.
- `medium`: relevant code/logic exists but no test proof.
- `low`: weak relevance signals only.
- `unknown`: inconclusive.

`applicability` must be an object with:

- `applies_to_oss_015`: boolean or null when unknown.
- `reason`: non-empty string.
- `affected_public_paths`: array of repository-relative public paths.
- `missing_public_paths`: array of repository-relative public paths.

`test_transplant` must be an object with:

- `attempted`: boolean.
- `result`: string or null when not attempted.
- `notes`: string or null.

`test_before_fix` must be an object with:

- `attempted`: boolean.
- `command`: string or null when not run.
- `exit_code`: integer or null when not run.
- `result`: string or null when not run.
- `log_path`: relative path under `output/logs/` or null when not run.

`fix_verification` must be an object with:

- `attempted`: boolean.
- `command`: string or null when not run.
- `exit_code`: integer or null when not run.
- `result`: string or null when not run.
- `patch_path`: relative path under `output/patches/` or null when no patch was written.
- `log_path`: relative path under `output/logs/` or null when not run.

`evidence` must be an array of objects. Each evidence object must include:

- `type`: one of `code_presence`, `logic_match`, `test_failure`, `test_pass`, `non_applicability`, `classification`, `infra_failure`, or `uncertainty`.
- `description`: non-empty string.
- Optional `path`, `log_path`, `patch_path`, `command`, and `exit_code` fields when they support the evidence.

All paths in JSON must be relative. Do not use absolute paths or `..` path segments. Repository paths must be repository-relative. Log paths must be under `output/logs/`. Patch paths must be under `output/patches/`.
Use null only for fields that are explicitly unavailable because a test, transplant, verification step, log, or patch was not attempted or not applicable.

Decision-specific requirements:

- `DIRECT_015_BUGFIX`: require `applicability.applies_to_oss_015: true` and `classification`, `code_presence`, or `logic_match` evidence showing this is a public OSS 0.15 bugfix candidate.
- `MASTER_FIX_VERIFIED_ON_015`: require `test_before_fix.attempted: true`, a non-zero `test_before_fix.exit_code`, `fix_verification.attempted: true`, `fix_verification.exit_code: 0`, a `fix_verification.patch_path`, at least one `test_failure` evidence item, and at least one `test_pass` evidence item.
- `MASTER_REPRODUCED_ON_015`: require `test_before_fix.attempted: true`, a non-zero `test_before_fix.exit_code`, a `test_before_fix.log_path`, and `test_failure` evidence with the expected failure.
- `MASTER_POSSIBLY_APPLICABLE`: require `applicability.applies_to_oss_015: true` or null with a reason, plus `code_presence` or `logic_match` evidence.
- `MASTER_NOT_APPLICABLE`: require `applicability.applies_to_oss_015: false` and `non_applicability` evidence for absent file, class, module, feature, or bug introduction after 0.15.
- `DISCARDED_NON_BUGFIX`, `DISCARDED_DOCS_ONLY`, `DISCARDED_CI_ONLY`, and `DISCARDED_RELEASE_ONLY`: require `classification` evidence.
- `INCONCLUSIVE` and `NEEDS_HUMAN_REVIEW`: require `uncertainty` evidence and a clear `applicability.reason`.
- `FAILED_INFRA`: require `infra_failure` evidence and a command, log path, or input file that explains the tooling or environment failure.
