# Local Dashboard Workflow Design

## Goal

Specify the commit-based workflow and the authorized access to a configured
local fork before implementing it.

## Implementation scope and expected behavior

- Document the separate `serve` workflow, the durable scan and job state, and
  the operator confirmation required for adaptations.
- Authorize scoped private snapshot access only in the new local service.
- Keep task 029 and the archived PR milestones scoped to the public CLI.

## Affected files

- `AGENTS.md`
- `docs/backport_harness_design.md`
- `docs/backport_harness_implementation_steps.md`
- Task specifications 031 through 033

## Test plan

Review the new boundary, deployment defaults, write paths, and acceptance
criteria against the previous design and task 029.

## Assumptions and non-goals

This task changes documentation. Development verification uses synthetic
repositories and a fake provider.
