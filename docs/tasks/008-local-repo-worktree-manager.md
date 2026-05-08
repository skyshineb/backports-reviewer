# Local Repo and Worktree Manager

## Goal

Create public upstream clone and per-PR public OSS `0.15` worktrees without ever using private fork paths.

## Implementation Scope

- Create `backport_harness/repo_manager.py`.
- Create `backport_harness/worktree_manager.py`.
- Clone `local_repo.upstream_url` into `local_repo.repo_dir` if missing.
- Fetch configured branches before preparing worktrees.
- Verify existing remote URL matches the configured public upstream URL.
- Create clean detached worktrees from public upstream `origin/0.15`.
- Use the default layout `workspace/worktrees/pr-<number>-015/`.
- Remove stale worktrees only when they are under configured `worktree_dir` and are not the main upstream clone.
- Wrap Git subprocess calls in a helper that captures stdout/stderr and disables prompts.
- Add private-path checks needed for repo and worktree paths.

## Expected Behavior

- Upstream repo is cloned when absent.
- Branches are fetched.
- A clean detached `0.15` worktree is created for a PR.
- Existing stale worktree is replaced safely.
- Private paths and private remotes are rejected.

## Affected Modules or Commands

- `backport_harness/repo_manager.py`
- `backport_harness/worktree_manager.py`
- Security/path helper module if needed
- Optional debug command: `backport-harness prepare --pr 12345`

## Test Plan

- Mock Git subprocess calls for clone, fetch, remote URL check, and worktree creation.
- Verify expected argv and `GIT_TERMINAL_PROMPT=0`.
- Verify stale worktree removal is limited to configured safe paths.
- Verify private/forbidden path rejection.
- Verify remote mismatch is rejected.

## Assumptions and Explicit Non-goals

- The harness only works with public upstream `master` and `0.15`.
- No private fork remote may be inferred or used.
- This milestone does not invoke Codex.
- Worktrees are preserved on failed analysis by default; cleanup policy beyond safe stale replacement is out of scope.

