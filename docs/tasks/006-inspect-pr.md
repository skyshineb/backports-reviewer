# Inspect One PR

## Goal

Add a CLI command for detailed inspection of one saved PR before or after analysis.

## Implementation Scope

TBD from design docs before implementation. This milestone should show PR metadata, changed files, queue state, attempts, latest decision, evidence, logs, and human review status.

## Expected Behavior

- `backport-harness inspect --pr 12345` displays one saved PR.
- Missing PRs produce a clear error.
- Evidence and log paths are visible after analysis.

## Affected Modules or Commands

- Inspect command module
- Storage query helpers
- Command: `backport-harness inspect --pr`

## Test Plan

TBD. At minimum, cover missing PR, pre-analysis PR, post-analysis PR, changed files, evidence, and human review status.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- This command reads SQLite and stored paths only.
- This command does not invoke Codex.

