# Local Web Dashboard

## Goal

Give one local operator full control of the commit-based workflow in a browser.

## Implementation scope and expected behavior

- Add `backport-harness serve`, loopback HTTP, and the timeline, queue,
  and settings screens. Show descriptions, notes, results, and history.
- Expose profile editing, pause and resume, manual scan and rescan, retry,
  cancellation, Apply, Skip, custom prompts, and adaptation confirmation.
- Style the interface as an editorial engineering log with warm paper,
  drafting lines, serif headings, a terracotta accent, and an original ink
  illustration in an anime style. Support narrow screens and keyboard use.
- Document local deployment and the safe synthetic verification flow.

## Affected modules or commands

- `backport-harness serve`
- Dashboard HTTP server, static assets, and usage docs

## Test plan

Exercise the HTTP workflow on loopback with temporary Git repositories and a
fake provider. Check forms, content escaping, request validation, and the
CLI entry point. Run the full test suite.

## Assumptions and non-goals

The service runs for one operator on the machine hosting the fork. The browser
uses local assets and the local service.
