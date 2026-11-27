# Incremental Commit Scanning and Applicability

## Goal

Discover upstream fixes and check their mechanical applicability to a local fork.

## Implementation scope and expected behavior

- Add SQLite tables for the active profile, commit candidates, scans, jobs, and
  operator history alongside the public PR tables.
- Validate upstream repository and refs and resolve fork locations within
  deployment-approved roots. Fetch public history in a service-owned mirror.
- Traverse the first-parent chain from the configured base, checkpoint the
  cursor with discovered candidates, and support rescan after upstream rewrites.
- Import the target commit into the mirror and probe in a detached worktree.
  Distinguish clean, empty, conflict, and Git errors. Record the target SHA.

## Affected modules or commands

- Dashboard Git and storage modules and their SQLite migration

## Test plan

Use temporary Git repositories to check first-parent ranges, cursor replay,
rewrites, merges, clean picks, empty picks, conflicts, and failed Git commands.
Run the existing migration and storage tests.

## Assumptions and non-goals

Public upstream is configured by GitHub slug. The fork is configured by local
path and branch. Candidate discovery uses commit subjects.
