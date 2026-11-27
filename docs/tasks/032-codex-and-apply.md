# Static Codex Analysis and Local Apply

## Goal

Analyze conflicts and let an operator write fixes to the selected local branch.

## Implementation scope and expected behavior

- Poll every 30 minutes by default. Keep scan and commit work independent of
  the single Codex worker. Limit automated analysis starts per scan interval.
- Expose only bounded read operations on a pinned fork snapshot to the Codex
  model through the OpenAI Responses API. Use `high` reasoning and validate
  replies before saving recommendations or preparing a patch.
- Support custom analysis prompts, skip and unskip, durable retries,
  cancellation, progress, and attempt history.
- Apply clean fixes directly on request. For conflicts, stage and validate the
  patch, show its exact diff, and require confirmation before writing the branch.
- Update refs with an expected old SHA and a durable operation marker. Recover
  interrupted writes and reject updates to a branch in a user checkout.

## Affected modules or commands

- Dashboard Codex, worker, Git, and storage modules

## Test plan

Exercise Git and fake-provider integration for direct application, adaptation,
invalid output, cancellation, double clicks, stale previews, and restart recovery.

## Assumptions and non-goals

The worker uses an OpenAI API credential supplied at deployment. Repository
access consists of static reads and Git plumbing. Remote fork writes, builds,
and test execution are outside this workflow.
