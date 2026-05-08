# Human Review Status

## Goal

Store human review outcomes for candidate PRs and surface that status in inspection and reports.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement the `review` command, allowed statuses, comment storage, and report/inspect integration.

## Expected Behavior

- Humans can mark a PR accepted, rejected, already present, not needed, backported, or failed to backport.
- Reports and inspect output show the latest review status.

## Affected Modules or Commands

- Review command module
- Human review storage helpers
- Inspect and report integrations
- Command: `backport-harness review`

## Test Plan

TBD. At minimum, cover status creation, status update, invalid status rejection, comment storage, inspect output, and report output.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- The harness records review state but does not perform private-fork backports.

