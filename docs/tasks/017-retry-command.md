# Retry Command

## Goal

Allow selected failed or inconclusive PRs to be queued for another analysis attempt while preserving prior history.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement retry selection by status or PR number, max-attempt checks, and reset to `QUEUED_FOR_ANALYSIS`.

## Expected Behavior

- Failed infra PRs can be retried.
- Inconclusive PRs can be retried.
- One PR can be retried explicitly.
- Previous analysis runs and decisions remain visible.

## Affected Modules or Commands

- Retry command module
- Queue/storage helpers
- Command: `backport-harness retry`

## Test Plan

TBD. At minimum, cover retry by status, retry by PR, max attempts, non-retryable state rejection, and preservation of previous runs.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- Attempts increment when a new analysis starts, not when retry is queued.

