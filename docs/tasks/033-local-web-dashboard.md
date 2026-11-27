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

## Illustration

The empty-state asset is
`backport_harness/dashboard/assets/drafting.webp`, generated with the built-in
imagegen tool.

> Create an original illustration-story bitmap for the empty state of an understated engineering dashboard. One adult engineer in rolled-up sleeves, quietly laying a partly rolled architectural blueprint flat on a small drawing table, shown from a three-quarter view. Render in refined hand-inked anime linework with thin contours, a little pen hatching and simple cel shadows. Use graphite ink, muted slate-blue drawing lines, warm cream clothing and a tiny muted terracotta accent. Keep the silhouette and interior detail readable at 200 pixels wide. Horizontally composed, isolated transparent background, no scenery outside the drawing table, no border. No text, no numerals, no logos, no signature.
