# Inspect One PR

## Goal

Add a CLI command for detailed inspection of one saved PR before or after analysis.

## Implementation Scope

- Add `backport-harness inspect --pr 12345`.
- Read one saved PR from SQLite by GitHub PR number.
- Show saved PR metadata, changed files, queue state, latest decision, evidence, related analysis logs, test runs, and latest human review status.
- Render readable terminal output suitable for deciding whether and how to analyze a PR.
- Return a clear error when the requested PR is not saved locally.

## Expected Behavior

- `backport-harness inspect --pr 12345` displays one saved PR.
- Missing PRs produce a clear error.
- Pre-analysis PRs show metadata, changed files, and queue state.
- Post-analysis PRs show the latest decision, related evidence, analysis run paths, test runs, and human review status when present.
- The command reads local SQLite only and never contacts GitHub or invokes Codex.

## Affected Modules or Commands

- `backport_harness/commands/inspect_pr.py`
- Storage query helpers
- Command: `backport-harness inspect --pr`

## Test Plan

- Cover missing PR behavior.
- Cover pre-analysis PR metadata, queue state, and changed files.
- Cover latest decision selection when multiple decisions exist.
- Cover evidence rows for the latest decision.
- Cover analysis run log paths for the latest decision.
- Cover test run display for the latest decision's analysis run.
- Cover latest human review status.
- Cover CLI help and rendered inspect output.

## Assumptions and Explicit Non-goals

- This command reads SQLite and stored paths only.
- This command does not invoke Codex.
- This command does not scan GitHub.
- This command does not mutate queue, decision, review, or PR state.
- JSON output is out of scope for this milestone.
