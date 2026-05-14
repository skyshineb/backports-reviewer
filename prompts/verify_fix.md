# Verify Public OSS 0.15 Fix

## Security Boundary

Use only public upstream data included in the task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If the fix cannot be adapted or verified from public context, choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Responsibility

Adapt the public upstream fix to the public OSS 0.15 worktree only when the bug has been reproduced or strong public evidence supports verification.
Run the focused public test again when available.
Save any adapted patch under `output/patches/` and logs under `output/logs/`.

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
Evidence must reference only public files, public commands, patches, or public logs from this task bundle.
Do not silently discard uncertain cases.
