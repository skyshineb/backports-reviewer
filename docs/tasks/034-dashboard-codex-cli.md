# Dashboard Codex CLI Authentication

## Goal

Allow a local dashboard operator to use the existing Codex ChatGPT login
for static analysis and adaptation.

## Implementation scope and expected behavior

- Add `serve --codex-backend cli`. Use a locally installed Codex CLI and its
  saved ChatGPT login. Keep the Responses API backend selectable as `api`.
- Run each job non-interactively with high reasoning, a temporary working
  directory, a restricted permission profile, and no shell, browser, hooks,
  plugins, or inherited user MCP configuration. Keep credentials in Codex.
- Provide bounded snapshot reads through a dedicated stdio MCP server.
  Validate CLI output with the same result and evidence rules as the API.
- Report installation, login, timeout, and invalid result failures through
  the existing worker UI. Cancel CLI processes when a job is canceled.

## Affected modules or commands

- Dashboard Codex backend, snapshot tools, UI status, and usage
- `backport-harness serve`

## Test plan

Exercise safe CLI arguments, credential environment filtering, schema and
evidence validation, the pinned MCP snapshot, failure and cancellation,
and CLI entry-point wiring. Use synthetic repositories for integration.
Run existing dashboard tests and the full suite.

## Assumptions and non-goals

The CLI runs as the user who authenticated it. This task adds an explicit
backend selection to the workflow from tasks 032 and 033. It does not change
which code is eligible for analysis, patch confirmation, or Git writes.
