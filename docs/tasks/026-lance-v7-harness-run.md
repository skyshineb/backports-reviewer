# Lance v7.0.0 Harness Run

## Goal

Adapt the public backport harness so it can run against a configured upstream
target ref, then use it for a Lance `v7.0.0` analysis run from upstream
`main`.

The configured Lance run is:

- repository: `lance-format/lance`
- upstream branch: `main`
- target ref: `refs/tags/v7.0.0`
- target label: `v7.0.0`

## Implementation Scope

- Add generic target-ref configuration while preserving the existing Hudi
  defaults:
  - default label/ref/suffix remains `0.15` / `origin/release-0.15.0` / `015`
  - Lance config uses `v7.0.0` / `refs/tags/v7.0.0` / `v7.0.0`
- Replace hardcoded `0.15` worktree preparation behavior with configured target
  worktree preparation.
- Keep compatibility wrappers where they are useful for existing call sites and
  tests.
- Relax Codex result validation so configured upstream branches such as `main`
  are accepted where the result currently allows only `master`/`0.15`.
- Update prompt and UI wording from Hudi-specific branch language to generic
  "configured public target ref" language.
- Update design and implementation-step documentation where needed to make the
  configured public target-ref behavior explicit before coding.
- Add `config.lance-v7.yaml` with Lance public workspace paths under
  `workspace/lance-v7/` and reports under `reports/lance-v7/`.
- Run the Lance operational batches described below after the generic target-ref
  readiness work is verified.
- Append major commands, result summaries, and decisions to this task journal.

## Expected Behavior

- Existing Hudi-oriented tests and default config behavior continue to use
  `origin/release-0.15.0` and `015` worktree suffixes unless overridden.
- Lance commands prepare target worktrees from `refs/tags/v7.0.0` and use
  Lance-specific workspace/report paths.
- Task bundles and prompts describe the configured public target ref instead of
  assuming a `0.15` branch.
- Codex result JSON with `target_branch: "main"` validates when the active
  upstream branch is `main`.
- The scanner can store and prioritize Lance `main` PRs merged since the release
  date window start.
- Analysis can be piloted on selected public PRs without accessing private forks,
  private patches, private history, or private test results.

## Affected Modules or Commands

- `backport_harness/config.py`
- `backport_harness/worktree_manager.py`
- `backport_harness/repo_manager.py`
- `backport_harness/task_builder.py`
- `backport_harness/codex_result.py`
- `backport_harness/result_validator.py`
- `backport_harness/analysis_runner.py`
- `backport_harness/commands/analyze.py`
- `backport_harness/commands/inspect_pr.py`
- `backport_harness/commands/list_prs.py`
- `prompts/analyze_master_pr.md`
- `prompts/analyze_015_pr.md`
- `prompts/transplant_test.md`
- `prompts/verify_fix.md`
- `config.yaml`
- `config.lance-v7.yaml`
- focused tests for config, worktree management, task building, prompts,
  result schema, validation, and analysis flow
- operational commands:
  - `backport-harness db init`
  - `backport-harness scan`
  - `backport-harness list-prs`
  - `backport-harness inspect`
  - `backport-harness prepare`
  - `backport-harness prepare-bundle`
  - `backport-harness analyze`
  - `backport-harness recover-stale`
  - `backport-harness retry`
  - `backport-harness report`

## Test Plan

- Compare this task against:
  - `docs/backport_harness_design.md`
  - `docs/backport_harness_implementation_steps.md`
  - relevant existing task files in `docs/tasks/`
- Run focused tests:
  - `pytest tests/test_config.py`
  - `pytest tests/test_worktree_manager.py`
  - `pytest tests/test_repo_manager.py`
  - `pytest tests/test_task_builder.py`
  - `pytest tests/test_prompt_templates.py`
  - `pytest tests/test_codex_result.py`
  - `pytest tests/test_result_validator.py`
  - `pytest tests/test_analysis_runner.py`
  - `pytest tests/test_analysis_flow.py`
- Run the full test suite:
  - `pytest`
- For the Lance operation, run safe public/test commands:
  - `db init`
  - `scan` in the specified date windows
  - `list-prs --order-by priority`
  - `prepare` and `prepare-bundle` for one Lance PR
  - `analyze --dry-run --limit 10`
  - one-PR pilot analysis commands as appropriate
  - `recover-stale`
  - retry checks
  - `report`

## Assumptions and Explicit Non-goals

- `v7.0.0` is a tag, not a branch; the target ref is
  `refs/tags/v7.0.0`.
- `2026-05-28` is the date-only scan start for post-release Lance PRs.
- GitHub authentication may be read from `~/gh_token` only at command runtime and
  must never be printed or written to the journal.
- The implementation must preserve the security boundary: do not access private
  forks, private patches, private repository history, or private test results.
- This task does not change the product decision model beyond replacing
  hardcoded target-branch assumptions with configured public refs.
- This task does not require a GitHub branch named `v7.0.0`.
- The initial analysis queue should prioritize likely bugfix PRs before default
  priority PRs.
- If GitHub push or PR creation is unavailable, leave the branch and commit ready
  locally and report exactly what remains.

## Operational Batches

### Batch 0: Generic Target-Ref Readiness

- Implement and verify generic target-ref support.
- Run `prepare` and `prepare-bundle` for one Lance PR.

### Batch 1: Lance Scans

Scan `main` in date windows:

- `2026-05-28..2026-05-31`: expected 27 PRs
- `2026-06-01..2026-06-07`: expected 74 PRs
- `2026-06-08..2026-06-14`: expected 43 PRs
- `2026-06-15..2026-06-21`: expected 51 PRs
- `2026-06-22..2026-06-25`: expected 47 PRs

### Batch 2: Pilot Analysis

- Run a 10-PR pilot with `analyze --dry-run --limit 10`.
- Run `analyze --pr` one PR at a time for selected pilot PRs.

### Batch 3: Priority Queue

- Analyze the 86 likely bugfix PRs plus 3 ambiguous repair PRs first.
- Use batches of 5 where batch mode is appropriate.

### Batch 4: Remaining Queue

- Analyze the remaining 153 default-priority PRs after the high-value queue.

## Planning Investigation Log

- Inspected repository documentation and implementation areas during planning,
  including design docs, usage docs, config, CLI commands, worktree manager, task
  builder, prompts, and result schema.
- Found harness repo state during planning: branch `task/022-documentation` with
  untracked `workspace/`.
- Found hardcoded limitations during planning:
  - `0.15` worktree ref
  - `0.15` prompt wording
  - result schema restricted to `master`/`0.15`
- Gathered GitHub facts during planning:
  - release published at `2026-05-27T21:47:17Z`
  - no GitHub branch named `v7.0.0`
  - first post-release `main` commit:
    `30184975fd1d351baa0913d9bca0b6f65fd07384`
  - estimated 276 commits after the release timestamp
  - `v7.0.0...main` compare showed `main` ahead by 302 and the tag behind by 2
    because the refs diverged
  - merged `main` PR estimate for `2026-05-28` through `2026-06-25`: 242
  - priority estimate: 86 likely bugfix PRs, 3 ambiguous repair PRs, 153 default
    priority PRs
- Decisions made during planning:
  - implement generic target-ref adaptation before running Lance operations
  - use bugfix-first batching
  - use `2026-05-28` as the date-only scan start

## Execution Journal

- Created work context on `2026-06-25`.
- Ran `git status --short --branch`: current repo was
  `task/022-documentation...origin/task/022-documentation` with untracked
  `workspace/`.
- Ran `git fetch origin main`: refreshed `origin/main` from `10c28ef` to
  `2b693a8`.
- Ran `git checkout -B task/026-lance-v7-harness-run origin/main`: created and
  checked out the task branch from current `origin/main`.
- Created this task file before implementation.
- Compared the task with the design and implementation-step docs. Found the
  existing docs were Hudi-specific (`master`/`0.15`) while this task requires a
  generic public target ref. Decision: update docs first to preserve Hudi
  defaults and explicitly allow configured public target refs.
- Updated docs, config, worktree preparation, task bundle instructions, prompt
  wording, result parsing, runtime result validation, and tests for configured
  public target refs.
- Added `config.lance-v7.yaml` with Lance public paths under
  `workspace/lance-v7/` and reports under `reports/lance-v7/`.
- Ran focused tests for config, worktree manager, repo manager, task builder,
  prompts, Codex result schema, result validator, analysis runner, and analysis
  flow: 135 passed.
- Ran full `pytest`: 272 passed.
- Ran Lance DB initialization with `config.lance-v7.yaml`: database created under
  `workspace/lance-v7/backport_harness.sqlite3`.
- Ran Lance scans with `GITHUB_TOKEN` read from `~/gh_token` only at command
  runtime:
  - `2026-05-28..2026-05-31`: saw 27 PRs, saved 27 PRs
  - `2026-06-01..2026-06-07`: saw 74 PRs, saved 74 PRs
  - `2026-06-08..2026-06-14`: saw 43 PRs, saved 43 PRs
  - `2026-06-15..2026-06-21`: saw 51 PRs, saved 51 PRs
  - `2026-06-22..2026-06-25`: saw 47 PRs, saved 47 PRs
- Ran `list-prs --order-by priority`: confirmed the queued PRs sort with
  high-priority likely bugfixes first; first selected PR was #6963.
- Ran `prepare --pr 6963`: created
  `workspace/lance-v7/worktrees/pr-6963-v7.0.0`.
- Ran `prepare-bundle --pr 6963`: created
  `workspace/lance-v7/tasks/pr-6963`.
- Verified the #6963 generated instructions render `Target branch: main`,
  `Configured public target ref: v7.0.0 (refs/tags/v7.0.0)`, and the generic
  target-ref worktree line.
- Verified the #6963 worktree HEAD is exactly tag `v7.0.0`.
- Ran `analyze --dry-run --limit 10`: selected the first ten priority-20 Lance
  PRs, starting with #6963.
- Ran `analyze --pr 6963`: Codex exited 0 without timeout; result validated and
  stored as `MASTER_FIX_VERIFIED_ON_015` / `very_high`.
- Ran `inspect --pr 6963`: confirmed queue status `REPORTABLE`, one attempt,
  target branch `main`, and validated evidence/test logs for the reproduced and
  verified JNI binding fix.
- Ran `recover-stale`: recovered 0 stale Codex runs.
- Ran `retry --status NEEDS_RETRY --limit 5`: retried 0 PRs.
- Ran `retry --status FAILED_INFRA --limit 5`: retried 0 PRs.
- Ran `report`: generated `reports/lance-v7/` with 1 backport candidate, 0
  inconclusive rows, 0 discarded rows, and 242 full-audit rows.
- Queried Lance queue counts:
  - `REPORTABLE`: 1
  - `QUEUED_FOR_ANALYSIS`: 241
  - priority 20: 86
  - priority 50: 3
  - priority 100: 153
  - decision `MASTER_FIX_VERIFIED_ON_015`: 1
- Reran expanded focused tests after cleanup: 187 passed.
- Reran full `pytest` after cleanup: 272 passed.
- Committed implementation and run artifacts as
  `c33002e Run Lance v7 target-ref harness pilot`.
- Pushed branch `task/026-lance-v7-harness-run` to origin.
- Created GitHub PR: `https://github.com/skyshineb/backports-reviewer/pull/28`.
- Resumed the Lance priority queue run on `2026-06-25` from branch
  `task/026-lance-v7-harness-run`.
- Ran `recover-stale`: recovered 0 stale Codex runs.
- Ran `analyze --dry-run --limit 5`: confirmed the next queued PRs were
  #6957, #6965, #6953, #6620, and #6989.
- Ran `analyze --pr 6957` and `inspect --pr 6957`: Codex exited 0 without
  timeout; result validated as `MASTER_FIX_VERIFIED_ON_015` / `very_high`;
  queue status `REPORTABLE`.
- Ran `analyze --pr 6965` and `inspect --pr 6965`: Codex exited 0 without
  timeout; result validated as `MASTER_FIX_VERIFIED_ON_015` / `very_high`;
  queue status `REPORTABLE`.
- Started `analyze --pr 6953`; after it was already running, operator
  direction changed to stop after two more PRs and check results.
- Ran `inspect --pr 6953`: Codex exited 0 without timeout; result validated as
  `DISCARDED_NON_BUGFIX` / `medium`; queue status `DONE`.
- Ran `analyze --pr 6620` and `inspect --pr 6620`: Codex exited 0 without
  timeout; result validated as `DISCARDED_NON_BUGFIX` / `medium`; queue status
  `DONE`.
- Stopped analysis before #6989 per operator direction.
- Ran `recover-stale`: recovered 0 stale Codex runs.
- Ran `report`: generated `reports/lance-v7/` with 3 backport candidates, 0
  inconclusive rows, 2 discarded rows, and 242 full-audit rows.
- Queried Lance queue and decision counts after the stopped run:
  - `REPORTABLE`: 3
  - `DONE`: 2
  - `QUEUED_FOR_ANALYSIS`: 237
  - priority 20 remaining queued: 81
  - priority 50 remaining queued: 3
  - priority 100 remaining queued: 153
  - decision `MASTER_FIX_VERIFIED_ON_015`: 3
  - decision `DISCARDED_NON_BUGFIX`: 2
- Next queued PR after the stopped run is #6989.
- Resumed the Lance priority queue run on `2026-06-25` from branch
  `task/027-codex-reasoning-effort`, which contains
  `codex.reasoning_effort: medium` in `config.lance-v7.yaml`.
- Ran `git status --short --branch`: current branch was
  `task/027-codex-reasoning-effort...origin/task/027-codex-reasoning-effort`
  with untracked `workspace/`.
- Ran `recover-stale`: recovered 0 stale Codex runs.
- Ran `analyze --dry-run --limit 5`: confirmed the next queued PRs were
  #6989, #6787, #6994, #6999, and #6998.
- Ran `analyze --pr 6989`: first attempt failed before Codex completion due to
  public `git fetch` DNS failure for `github.com`; queue status became
  `NEEDS_RETRY` with latest run status `FAILED_INFRA`.
- Ran `retry --pr 6989`, then reran `analyze --pr 6989` and `inspect --pr
  6989`: Codex exited 0 without timeout; result validated as
  `MASTER_FIX_VERIFIED_ON_015` / `very_high`; queue status `REPORTABLE`;
  attempts: 2.
- Ran `analyze --pr 6787`: first attempt exited 1 after Codex transport
  failures to `chatgpt.com` and HTTPS fallback `403 Forbidden`; queue status
  became `NEEDS_RETRY` with latest run status `FAILED_INFRA`.
- Ran `retry --pr 6787`, then reran `analyze --pr 6787` and `inspect --pr
  6787`: Codex exited 0 without timeout; result validated as
  `MASTER_REPRODUCED_ON_015` / `high`; queue status `REPORTABLE`; attempts: 2.
- Stopped analysis before #6994 per operator direction.
- Ran `recover-stale`: recovered 0 stale Codex runs.
- Ran `report`: generated `reports/lance-v7/` with 5 backport candidates, 0
  inconclusive rows, 2 discarded rows, and 242 full-audit rows.
- Queried Lance queue and decision counts after the stopped run:
  - `REPORTABLE`: 5
  - `DONE`: 2
  - `QUEUED_FOR_ANALYSIS`: 235
  - priority 20 remaining queued: 79
  - priority 50 remaining queued: 3
  - priority 100 remaining queued: 153
  - decision `MASTER_FIX_VERIFIED_ON_015`: 4
  - decision `MASTER_REPRODUCED_ON_015`: 1
  - decision `DISCARDED_NON_BUGFIX`: 2
- Queried analysis run counts after the stopped run:
  - `VALIDATED`: 7
  - `FAILED_INFRA`: 2
- Ran `analyze --dry-run --limit 5`: confirmed the next queued PRs are #6994,
  #6999, #6998, #7004, and #6995.
