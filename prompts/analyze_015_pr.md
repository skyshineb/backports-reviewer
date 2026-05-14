# Analyze Upstream 0.15 PR

## Security Boundary

Use only public upstream data included in the task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If a question cannot be answered from public upstream context, say so and choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Inputs

- PR metadata: `pr.json`
- Changed files: `files_changed.json`
- Public PR diff: `pr.diff`
- Public OSS 0.15 worktree path supplied by the task builder

## Responsibility

Decide whether this PR merged into upstream `0.15` is a real bugfix candidate for human backport review.
Do not silently discard uncertain cases.

## Allowed Decisions

- `DIRECT_015_BUGFIX`
- `DISCARDED_NON_BUGFIX`
- `DISCARDED_DOCS_ONLY`
- `DISCARDED_CI_ONLY`
- `DISCARDED_RELEASE_ONLY`
- `NEEDS_HUMAN_REVIEW`
- `INCONCLUSIVE`
- `FAILED_INFRA`

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

- `very_high`: a focused public test fails before the adapted fix and passes after it.
- `high`: a focused public test reproduces the bug on OSS 0.15.
- `medium`: affected public code or equivalent logic exists but there is no test proof.
- `low`: only weak public relevance signals exist.
- `unknown`: the result is inconclusive.

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
