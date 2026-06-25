# Analyze Upstream 0.15 PR

## Security Boundary

Use only public upstream data included in the task bundle and the configured public target-ref worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If a question cannot be answered from public upstream context, say so and choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Inputs

- PR metadata: `pr.json`
- Changed files: `files_changed.json`
- Public PR diff: `pr.diff`
- Configured public target ref from the rendered task context line `Configured public target ref: <label> (<ref>)`
- Configured public target-ref worktree from the rendered task context line `Configured public target-ref worktree: <path>`

## Responsibility

Decide whether this PR merged into the configured public target branch is a real bugfix candidate for human backport review.
Do not silently discard uncertain cases.

## No-Test Policy

Do not discard a PR only because no regression test exists.
Use `INCONCLUSIVE` when applicability is unsafe to determine from public context.

## Test Execution Limits

Run the smallest focused command that can verify the behavior.
Prefer commands in this order: single test method, then test class, then test module.
Avoid full project tests unless no narrower command can verify the behavior.
Record every executed command, exit code, and related log path in `output/codex_result.json`.
Save every test or command log under `output/logs/`.

## Modification Boundaries

Only edit files in the configured public target-ref worktree that are needed for transplant or fix verification.
Do not modify task input files, including `pr.json`, `files_changed.json`, and `pr.diff`.
Write any generated patch under `output/patches/`.
Write human-readable notes to `output/notes.md`.
Do not write prose outside `output/codex_result.json` and `output/notes.md`.

## Allowed Decisions

- `DIRECT_015_BUGFIX`
- `DISCARDED_NON_BUGFIX`
- `DISCARDED_DOCS_ONLY`
- `DISCARDED_CI_ONLY`
- `DISCARDED_RELEASE_ONLY`
- `NEEDS_HUMAN_REVIEW`
- `INCONCLUSIVE`
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
- `high`: regression test reproduces the bug on the configured public target ref.
- `medium`: relevant code/logic exists but no test proof.
- `low`: weak relevance signals only.
- `unknown`: inconclusive.

`applicability` must be an object with:

- `applies_to_oss_015`: boolean or null when unknown.
- `reason`: non-empty string.
- `affected_public_paths`: array of repository-relative public paths.
- `missing_public_paths`: array of repository-relative public paths.

The `applies_to_oss_015` field retains its historical name; interpret it as applicability to the configured public target ref for this task.

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

Allowed result values:

- `test_transplant.result`: `not_found`, `not_applicable`, `applied`, `applied_and_compiled`, `does_not_compile`, `failed`, `skipped`, or null.
- `test_before_fix.result`: `not_run`, `passed`, `failed`, `failed_with_expected_error`, `failed_with_unrelated_error`, `did_not_compile`, `flaky`, `timeout`, `infra_failed`, or null.
- `fix_verification.result`: `not_run`, `passed_after_adapted_fix`, `failed_after_adapted_fix`, `patch_not_applicable`, `did_not_compile`, `flaky`, `timeout`, `infra_failed`, or null.

Do not invent result values. If a command cannot start because local tooling or
test infrastructure is unavailable, such as missing `mvn`, use `infra_failed`,
record the command, exit code, and log path when available, and add
`infra_failure` evidence.

`evidence` must be an array of objects. Each evidence object must include:

- `type`: one of `code_presence`, `logic_match`, `test_failure`, `test_pass`, `non_applicability`, `classification`, `infra_failure`, or `uncertainty`.
- `description`: non-empty string.
- Optional `path`, `log_path`, `patch_path`, `command`, and `exit_code` fields when they support the evidence.

All paths in JSON must be relative. Do not use absolute paths or `..` path segments. Repository paths must be repository-relative. Log paths must be under `output/logs/`. Patch paths must be under `output/patches/`.
Use null only for fields that are explicitly unavailable because a test, transplant, verification step, log, or patch was not attempted or not applicable.

Decision-specific requirements:

- `DIRECT_015_BUGFIX`: require `applicability.applies_to_oss_015: true` and `classification`, `code_presence`, or `logic_match` evidence showing this is a configured public target-ref bugfix candidate.
- `MASTER_FIX_VERIFIED_ON_015`: require `test_before_fix.attempted: true`, a non-zero `test_before_fix.exit_code`, `fix_verification.attempted: true`, `fix_verification.exit_code: 0`, a `fix_verification.patch_path`, at least one `test_failure` evidence item, and at least one `test_pass` evidence item.
- `MASTER_REPRODUCED_ON_015`: require `test_before_fix.attempted: true`, a non-zero `test_before_fix.exit_code`, a `test_before_fix.log_path`, and `test_failure` evidence with the expected failure.
- `MASTER_POSSIBLY_APPLICABLE`: require `applicability.applies_to_oss_015: true` or null with a reason, plus `code_presence` or `logic_match` evidence.
- `MASTER_NOT_APPLICABLE`: require `applicability.applies_to_oss_015: false` and `non_applicability` evidence for absent file, class, module, feature, bug introduction after the configured target ref, or fix behavior already present in the configured public target ref.
- `DISCARDED_NON_BUGFIX`, `DISCARDED_DOCS_ONLY`, `DISCARDED_CI_ONLY`, and `DISCARDED_RELEASE_ONLY`: require `classification` evidence.
- `INCONCLUSIVE` and `NEEDS_HUMAN_REVIEW`: require `uncertainty` evidence and a clear `applicability.reason`.
- `FAILED_INFRA`: require `infra_failure` evidence and a command, log path, or input file that explains the tooling or environment failure.
