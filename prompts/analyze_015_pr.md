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
