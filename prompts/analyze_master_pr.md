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

## Strict JSON Output

Write strict JSON only to `output/codex_result.json`.
The JSON object must include:

- `schema_version`
- `pr_number`
- `target_branch`
- `decision`
- `confidence`
- `summary`
- `human_action`
- `evidence`

Use `schema_version: 1`.
Use only the allowed decision values listed above.
Evidence must reference only public files, public commands, or public logs from this task bundle.
