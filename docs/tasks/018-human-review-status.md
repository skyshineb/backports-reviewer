# Human Review Status

## Goal

Store human review outcomes for candidate PRs and surface that status in inspection and reports.

## Implementation Scope

- Implement `backport-harness review` for saved PRs.
- Validate human review statuses against the milestone-approved set.
- Store review status rows in SQLite with optional comments.
- Surface command-created review rows through the existing inspect and report read paths.
- Keep review history append-only; a newer row becomes the latest review.

## Expected Behavior

- Humans can mark a PR as pending, accepted for backport, rejected, already present, not needed, backported, or failed to backport.
- Humans can attach an optional comment to explain the private-fork review outcome.
- The command rejects unknown PRs and invalid statuses with clear CLI errors.
- Reports and inspect output show the latest review status and comment.

## Affected Modules or Commands

- Review command module
- Human review storage helpers
- Inspect and report integrations
- Command: `backport-harness review`

## Test Plan

- Cover status creation for an existing saved PR.
- Cover latest-review behavior by inserting more than one review row for a PR.
- Cover invalid status rejection.
- Cover missing PR rejection.
- Cover optional comment storage.
- Cover inspect output for command-created review status and comment.
- Cover report output for command-created review status in Markdown and JSONL.

## Assumptions and Explicit Non-goals

- The harness records review state but does not perform private-fork backports.
- The existing nullable `reviewer` column remains for schema compatibility, but task 018 does not expose a reviewer CLI option and command-created rows store `reviewer` as null.
- Review status does not change report categorization or queue state.
- This task does not add schema migrations because the `human_reviews` table already exists.
