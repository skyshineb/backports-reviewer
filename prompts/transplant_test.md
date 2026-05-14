# Transplant Public Regression Test

## Security Boundary

Use only public upstream data included in the task bundle and the public OSS 0.15 worktree.
Do not use, request, infer, or reference private fork code, private patches, private repository history, private test data, private business logic, or private paths.
If a regression test cannot be transplanted from public context, choose `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`.

## Responsibility

Identify a focused public regression test from the PR when one exists.
Attempt to adapt it to the public OSS 0.15 worktree using only public code.
Record the command, exit code, result, and log path under `output/logs/`.

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
Evidence must reference only public files, public commands, or public logs from this task bundle.
Do not silently discard uncertain cases.
