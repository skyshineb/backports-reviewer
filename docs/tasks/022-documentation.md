# Documentation

## Goal

Document setup, security boundaries, workflows, and troubleshooting so a new engineer can operate the harness safely.

## Implementation Scope

TBD from design docs before implementation. This milestone should update README and usage documentation for config, GitHub token setup, scanning, listing, inspection, analysis, retry, stale recovery, reports, and human review.

## Expected Behavior

- A new engineer can set up the tool.
- A new engineer can run scanner and listing workflows.
- A new engineer can analyze a limited batch.
- A new engineer can regenerate reports and understand known safety boundaries.

## Affected Modules or Commands

- `README.md`
- Any docs under `docs/`
- Example config or workflow snippets

## Test Plan

TBD. At minimum, verify documented commands match implemented CLI names and options.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- Documentation must reiterate that the harness never accesses private forks, private patches, private history, or private test data.

