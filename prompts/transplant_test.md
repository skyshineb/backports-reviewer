# Transplant Public Regression Test

## Security Boundary

Use only public upstream data included in the task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If a regression test cannot be transplanted from public context, choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Responsibility

Identify a focused public regression test from the PR when one exists.
Attempt to adapt it to the public OSS 0.15 worktree using only public code.
Record the command, exit code, result, and log path under `output/logs/`.

## No-Test Policy

Do not discard a PR only because no regression test exists.
Use `MASTER_POSSIBLY_APPLICABLE` when relevant public OSS 0.15 code or logic exists but there is no test proof.
Use `INCONCLUSIVE` when applicability is unsafe to determine from public context.

## Test Transplant Outcome Policy

- No public regression test found: use `MASTER_POSSIBLY_APPLICABLE` when relevant public OSS 0.15 code or logic exists; otherwise use `INCONCLUSIVE`.
- Test not applicable to public OSS 0.15: use `INCONCLUSIVE`.
- Transplanted test does not compile: use `INCONCLUSIVE`.
- Transplanted test fails with the expected bug before fix: use `MASTER_REPRODUCED_ON_015`.
- Transplanted test fails with an unrelated error: use `INCONCLUSIVE`.
- Transplanted test passes before fix: use `MASTER_POSSIBLY_APPLICABLE` when relevant public OSS 0.15 code or logic exists; otherwise use `INCONCLUSIVE`.
- Transplanted test is flaky: use `INCONCLUSIVE`.

## Test Execution Limits

Run the smallest focused command that can verify the behavior.
Prefer commands in this order: single test method, then test class, then test module.
Avoid full project tests unless no narrower command can verify the behavior.
Record every executed command, exit code, and related log path in `output/codex_result.json`.
Save every test or command log under `output/logs/`.

## Modification Boundaries

Only edit files in the public OSS 0.15 worktree that are needed for transplant or fix verification.
Do not modify task input files, including `pr.json`, `files_changed.json`, and `pr.diff`.
Write any generated patch under `output/patches/`.
Write human-readable notes to `output/notes.md`.
Do not write prose outside `output/codex_result.json` and `output/notes.md`.

## Allowed Decisions

- `MASTER_REPRODUCED_ON_015`
- `MASTER_POSSIBLY_APPLICABLE`
- `INCONCLUSIVE`
- `NEEDS_HUMAN_REVIEW`
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
Write human-readable notes only to `output/notes.md`.
Do not write prose outside `output/codex_result.json` and `output/notes.md`.
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

- `MASTER_REPRODUCED_ON_015`: require `test_transplant.attempted: true`, `test_transplant.result: applied` or `applied_and_compiled`, `test_before_fix.attempted: true`, a non-zero `test_before_fix.exit_code`, a `test_before_fix.log_path`, and `test_failure` evidence with the expected failure.
- `MASTER_POSSIBLY_APPLICABLE`: require `applicability.applies_to_oss_015: true` or null with a reason, plus `code_presence` or `logic_match` evidence.
- `INCONCLUSIVE` and `NEEDS_HUMAN_REVIEW`: require `uncertainty` evidence and a clear `applicability.reason`.
- `FAILED_INFRA`: require `infra_failure` evidence and a command, log path, or required input file that identifies one of the failures allowed by the `FAILED_INFRA` policy.

Do not silently discard uncertain cases.
