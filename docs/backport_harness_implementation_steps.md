# Backport Harness Implementation Steps

## 1. Implementation goal

Build a Python-based Backport Harness that:

- Scans public upstream PRs merged into `master` and `0.15`.
- Supports historical catch-up via `--from-date` and `--to-date`.
- Stores all data in SQLite.
- Lets users list and inspect saved PRs before analysis.
- Invokes Codex as a semantic code reasoning worker.
- Supports limited, resumable Codex analysis batches.
- Recovers stale Codex runs after a default 2-hour timeout.
- Generates human review reports.
- Never accesses the private fork.

## 2. Delivery strategy

Implement in small milestones.

Recommended order:

1. Project skeleton.
2. SQLite schema and migrations.
3. Config and logging.
4. Slow GitHub scanner.
5. PR listing and inspection.
6. Analysis queue.
7. Worktree and task bundle preparation.
8. Codex runner with 2-hour timeout.
9. Codex result schema and validation.
10. Report generation.
11. Retry and stale recovery.
12. Human review status.
13. Test transplantation support.
14. Fix verification support.

---

## 3. Milestone 1: project skeleton

### Tasks

- Create Python project.
- Add `pyproject.toml`.
- Add package `backport_harness`.
- Add CLI entry point.
- Add basic logging.
- Add config loader.
- Add initial README.

### Suggested dependencies

- `typer` or `click` for CLI.
- `pydantic` for config and result schemas.
- `requests` or `httpx` for GitHub API.
- `rich` for readable CLI output.
- `pytest` for tests.
- `pyyaml` for config.
- Standard `sqlite3` or SQLAlchemy.

### Initial file structure

```text
backport-harness/
  pyproject.toml
  README.md
  config.yaml

  backport_harness/
    __init__.py
    main.py
    config.py
    logging_config.py

  tests/
    test_cli.py
```

### Acceptance criteria

- `backport-harness --help` works.
- `backport-harness version` works.
- Config loads from `config.yaml`.
- Logging prints useful messages.

---

## 4. Milestone 2: SQLite schema and migrations

### Tasks

- Implement `storage.py`.
- Add migration runner.
- Add `migrations/001_initial.sql`.
- Create tables:
  - `prs`
  - `pr_files`
  - `scan_runs`
  - `analysis_queue`
  - `analysis_runs`
  - `decisions`
  - `evidence`
  - `test_runs`
  - `human_reviews`

### Required command

```bash
backport-harness db init
```

Optional:

```bash
backport-harness db migrate
backport-harness db status
```

### Acceptance criteria

- DB file is created.
- Migrations are idempotent.
- Running migration twice is safe.
- Unit tests verify required tables exist.

---

## 5. Milestone 3: config model

### Tasks

Implement typed config:

```yaml
github:
  owner: apache
  repo: hudi
  branches:
    - master
    - "0.15"
  token_env: GITHUB_TOKEN
  request_delay_seconds: 1.0
  page_delay_seconds: 2.0
  max_retries: 5
  backoff_multiplier: 2.0
  respect_rate_limit: true

local_repo:
  upstream_url: https://github.com/apache/hudi.git
  repo_dir: "./workspace/upstream"
  worktree_dir: "./workspace/worktrees"

codex:
  command: "codex"
  mode: "exec"
  timeout_seconds: 7200
  max_attempts_per_pr: 2
  result_file: "output/codex_result.json"

analysis:
  default_limit: 5
  stale_timeout_seconds: 7200

reports:
  output_dir: "./reports"

storage:
  sqlite_path: "./workspace/backport_harness.sqlite3"
```

### Acceptance criteria

- Missing required config fields fail fast.
- Defaults are applied where appropriate.
- `timeout_seconds` defaults to 7200 seconds.
- GitHub token is read from environment variable configured by `token_env`.

---

## 6. Milestone 4: slow GitHub scanner

### Command

```bash
backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31
```

Optional branch filter:

```bash
backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31 --branch master
backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31 --branch 0.15
```

### Tasks

- Implement `github_client.py`.
- Query merged PRs by branch and merged date.
- Store PR metadata.
- Fetch changed files for each PR.
- Store changed files.
- Create/update `analysis_queue` row for each PR.
- Record scan in `scan_runs`.
- Add request delay.
- Add page delay.
- Respect GitHub rate-limit headers.
- Add exponential backoff.

### Important behavior

Use `merged_at` as the only date filter.

Meaning:

```text
--from-date = merged_at >= date
--to-date   = merged_at <= date
```

### Idempotency rules

- Re-scanning same range must not duplicate PRs.
- Existing PR records should be updated.
- Existing queue rows should not lose analysis state.
- Changed files may be refreshed.

### Acceptance criteria

- Can scan `master`.
- Can scan `0.15`.
- Can scan both when branch omitted.
- Can scan a historical range.
- Re-running same scan does not duplicate data.
- Slow scanning delay is visible in logs.
- Rate-limit response is handled gracefully.

---

## 7. Milestone 5: list saved PRs

### Command

```bash
backport-harness list-prs
```

Filters:

```bash
backport-harness list-prs --branch master
backport-harness list-prs --branch 0.15
backport-harness list-prs --status QUEUED_FOR_ANALYSIS
backport-harness list-prs --from-date 2024-01-01 --to-date 2024-12-31
backport-harness list-prs --limit 50
```

### Tasks

- Implement `commands/list_prs.py`.
- Join `prs`, `analysis_queue`, and latest `decisions`.
- Render concise table.
- Add filters.
- Add ordering by branch, priority, merged date, or status.

### Suggested output

```text
PR       Branch   Merged at    Queue status          Decision                  Title
#12345   0.15     2024-02-10   QUEUED_FOR_ANALYSIS   -                         Fix NPE in compaction
#12346   master   2024-02-12   DONE                  MASTER_NOT_APPLICABLE     Fix new feature bug
#12347   master   2024-02-14   REPORTABLE            MASTER_REPRODUCED_ON_015  Fix race in metadata table
```

### Acceptance criteria

- User can see all PRs saved in DB.
- User can filter by branch.
- User can filter by queue status.
- User can filter by date.
- Output is readable for deciding what to analyze next.

---

## 8. Milestone 6: inspect one PR

### Command

```bash
backport-harness inspect --pr 12345
```

### Tasks

Show:

- PR title.
- PR URL.
- Target branch.
- Merged commit.
- Merged date.
- Author.
- Changed files.
- Queue status.
- Attempts.
- Last error.
- Latest decision.
- Evidence.
- Test logs.
- Human review status.

### Acceptance criteria

- User can inspect one PR before analysis.
- User can inspect one PR after analysis.
- Evidence and log paths are visible when present.

---

## 9. Milestone 7: analysis queue and priority

### Tasks

- Implement `state_machine.py`.
- Add queue state transitions.
- Assign initial priority.
- Implement selection of queued PRs for analysis.
- Implement dry run.

### Priority rules

Suggested initial priority:

| Priority | Condition |
|---:|---|
| 10 | Target branch `0.15` |
| 20 | Master PR with labels/title indicating bug, regression, correctness, NPE, race, corruption, data loss |
| 50 | Master PR with ambiguous fix-like title |
| 100 | Everything else |

Lower number means higher priority.

### Command

```bash
backport-harness analyze --limit 10 --dry-run
```

### Acceptance criteria

- Queue rows are created by scan.
- Dry run shows selected PRs without invoking Codex.
- Highest priority PRs are selected first.
- Already completed PRs are skipped.

---

## 10. Milestone 8: local repo and worktree manager

### Tasks

- Implement `repo_manager.py`.
- Implement `worktree_manager.py`.
- Clone public upstream repo if missing.
- Fetch branches.
- Create clean OSS `0.15` worktree per PR.
- Remove worktree if configured.
- Prevent accidental use of private repo path.

### Commands

This may be internal, but useful for debugging:

```bash
backport-harness prepare --pr 12345
```

### Worktree layout

```text
workspace/worktrees/pr-12345-015/
```

### Acceptance criteria

- Upstream repo is cloned.
- Branches are fetched.
- Clean `0.15` worktree is created.
- Existing stale worktree is replaced safely.
- Private paths are never referenced.

---

## 11. Milestone 9: task bundle builder

### Tasks

- Implement `task_builder.py`.
- Generate task directory.
- Write:
  - `pr.json`
  - `files_changed.json`
  - `pr.diff`
  - `instructions.md`
  - output directories.

### Task layout

```text
workspace/tasks/pr-12345/
  pr.json
  files_changed.json
  pr.diff
  instructions.md
  oss_015_worktree/
  output/
    logs/
    patches/
```

### Acceptance criteria

- Task bundle contains all public context needed by Codex.
- Instructions differ for `master` and `0.15` PRs.
- Output directories are pre-created.
- Bundle does not include private repo data.

---

## 12. Milestone 10: Codex prompt templates

### Files

```text
prompts/analyze_015_pr.md
prompts/analyze_master_pr.md
prompts/transplant_test.md
prompts/verify_fix.md
```

### `analyze_015_pr.md` responsibilities

Codex should decide whether a PR merged into upstream `0.15` is a real bugfix and should be added to the backport queue.

Allowed decisions:

```text
DIRECT_015_BUGFIX
DISCARDED_NON_BUGFIX
DISCARDED_DOCS_ONLY
DISCARDED_CI_ONLY
DISCARDED_RELEASE_ONLY
NEEDS_HUMAN_REVIEW
INCONCLUSIVE
FAILED_INFRA
```

### `analyze_master_pr.md` responsibilities

Codex should:

- Classify whether PR is a real bugfix.
- Check whether affected code exists in public OSS `0.15`.
- Determine applicability.
- Optionally transplant tests.
- Optionally verify adapted fix.

Allowed decisions:

```text
MASTER_NOT_APPLICABLE
MASTER_POSSIBLY_APPLICABLE
MASTER_REPRODUCED_ON_015
MASTER_FIX_VERIFIED_ON_015
INCONCLUSIVE
NEEDS_HUMAN_REVIEW
DISCARDED_NON_BUGFIX
DISCARDED_DOCS_ONLY
DISCARDED_CI_ONLY
DISCARDED_RELEASE_ONLY
FAILED_INFRA
```

### Acceptance criteria

- Prompt clearly states security boundary.
- Prompt forbids use of private fork.
- Prompt requires strict JSON output.
- Prompt tells Codex not to silently discard uncertain cases.
- Prompt defines allowed decisions.

---

## 13. Milestone 11: Codex runner with 2-hour timeout

### Command

```bash
backport-harness analyze --limit 5
backport-harness analyze --pr 12345
```

### Tasks

- Implement `codex_runner.py`.
- Lock queue item.
- Mark status `CODEX_RUNNING`.
- Create `analysis_runs` row.
- Invoke Codex process.
- Enforce default 7200-second timeout.
- Capture stdout and stderr.
- Store log paths.
- Mark run status.

### Failure behavior

If Codex exits non-zero:

- Store stderr.
- Mark queue item `NEEDS_RETRY` or `FAILED_INFRA`.
- Increment attempts.
- Preserve task directory.

If Codex times out:

- Kill process.
- Mark run as timeout.
- Mark queue item `NEEDS_RETRY`.
- Store logs.

### Acceptance criteria

- Codex can be invoked for one PR.
- Timeout is enforced.
- Logs are captured.
- Queue state is updated.
- Failure does not corrupt DB.
- Process can be interrupted and recovered.

---

## 14. Milestone 12: Codex result schema

### Tasks

- Implement `codex_result.py`.
- Define Pydantic model for `codex_result.json`.
- Define enums:
  - decision
  - confidence
  - test result
  - evidence type.

### Required fields

- `schema_version`
- `pr_number`
- `target_branch`
- `decision`
- `confidence`
- `summary`
- `human_action`
- `evidence`

### Acceptance criteria

- Valid result parses successfully.
- Malformed result fails validation.
- Unknown decision fails validation.
- Unknown confidence fails validation.
- Unit tests cover valid and invalid examples.

---

## 15. Milestone 13: result validator

### Tasks

- Implement `result_validator.py`.
- Validate generic result schema.
- Validate decision-specific evidence.
- Validate log paths.
- Validate patch paths.
- Validate test exit codes against claimed result.

### Decision-specific validation

#### `MASTER_FIX_VERIFIED_ON_015`

Require:

- Test before fix attempted.
- Test before fix failed.
- Fix verification attempted.
- Fix verification passed.
- Patch path exists.
- Test failure evidence exists.
- Test pass evidence exists.

#### `MASTER_REPRODUCED_ON_015`

Require:

- Test before fix attempted.
- Test before fix failed.
- Test log exists.
- Expected failure reason exists.

#### `MASTER_NOT_APPLICABLE`

Require strong non-applicability reason:

- Affected file absent.
- Affected class absent.
- Affected module absent.
- Feature absent.
- Bug introduced after `0.15`.

#### `INCONCLUSIVE`

Require explicit reason.

### Acceptance criteria

- Invalid Codex claims are rejected.
- Invalid result marks PR as `NEEDS_RETRY` or `FAILED_INFRA`.
- Valid results are stored.
- Unit tests cover each decision type.

---

## 16. Milestone 14: decision storage

### Tasks

- Store latest Codex result in:
  - `decisions`
  - `evidence`
  - `test_runs`
- Update `analysis_queue`.
- Preserve previous decisions for audit.
- Mark queue status:
  - `REPORTABLE`
  - `DONE`
  - `NEEDS_RETRY`
  - `FAILED_INFRA`

### Acceptance criteria

- Valid Codex result becomes stored decision.
- Evidence rows are stored.
- Test run rows are stored.
- Previous analysis runs remain accessible.
- Latest decision is easy to query.

---

## 17. Milestone 15: report writer

### Command

```bash
backport-harness report
```

### Reports

Generate:

```text
reports/backport-candidates.md
reports/inconclusive.md
reports/discarded.jsonl
reports/full-audit.jsonl
```

### `backport-candidates.md`

Include:

- `DIRECT_015_BUGFIX`
- `MASTER_REPRODUCED_ON_015`
- `MASTER_FIX_VERIFIED_ON_015`
- `NEEDS_HUMAN_REVIEW`

Columns:

- PR
- Target branch
- Merged date
- Decision
- Confidence
- Summary
- Evidence summary
- Human action
- Human review status

### `inconclusive.md`

Include:

- `INCONCLUSIVE`
- `FAILED_INFRA`
- `NEEDS_RETRY`

### `discarded.jsonl`

Include:

- `MASTER_NOT_APPLICABLE`
- `DISCARDED_NON_BUGFIX`
- `DISCARDED_DOCS_ONLY`
- `DISCARDED_CI_ONLY`
- `DISCARDED_RELEASE_ONLY`

### `full-audit.jsonl`

Include every PR and all latest decision metadata.

### Acceptance criteria

- Reports can be regenerated any time.
- Reports do not require Codex.
- Markdown report is readable.
- JSONL reports are machine-readable.
- Human review status is included if available.

---

## 18. Milestone 16: recover stale runs

### Command

```bash
backport-harness recover-stale
```

Optional:

```bash
backport-harness recover-stale --older-than-hours 2
```

### Tasks

- Find queue items with `CODEX_RUNNING`.
- If `locked_at` older than 2 hours, mark `NEEDS_RETRY`.
- Update last error.
- Preserve analysis run.
- Do not delete logs.

### Acceptance criteria

- Stale runs are detected.
- Default stale timeout is 2 hours.
- Stale runs become retryable.
- Non-stale running items are not touched.

---

## 19. Milestone 17: retry command

### Commands

```bash
backport-harness retry --status FAILED_INFRA --limit 3
backport-harness retry --status INCONCLUSIVE --limit 3
backport-harness retry --pr 12345
```

### Tasks

- Select retryable PRs.
- Check max attempts.
- Reset queue status to `QUEUED_FOR_ANALYSIS`.
- Increment attempts only when new analysis starts.
- Preserve previous decisions and logs.

### Acceptance criteria

- Failed infra PRs can be retried.
- Inconclusive PRs can be retried.
- One PR can be retried explicitly.
- Previous analysis history remains visible.

---

## 20. Milestone 18: human review status

### Command

```bash
backport-harness review --pr 12345 --status accepted_for_backport --comment "Relevant to private fork"
```

Allowed statuses:

```text
pending
accepted_for_backport
rejected
already_present
not_needed
backported
failed_to_backport
```

### Tasks

- Implement `review` command.
- Store or update `human_reviews`.
- Include status in reports and `inspect`.

### Acceptance criteria

- Human can mark candidate as accepted.
- Human can mark candidate as rejected.
- Human can mark candidate as already present.
- Reports show review status.

---

## 21. Milestone 19: test transplantation support

This can be implemented after MVP is useful.

### Tasks for Codex

- Identify regression tests in PR.
- Transplant or adapt test to OSS `0.15`.
- Prefer focused test method.
- Run test.
- Capture logs.
- Return result.

### Harness tasks

- Validate test log paths.
- Store test command.
- Store exit code.
- Store result in `test_runs`.

### Possible outcomes

```text
test_not_found
test_not_applicable
test_does_not_compile
test_failed_with_expected_error
test_failed_with_unrelated_error
test_passed
test_flaky
```

### Acceptance criteria

- Codex can attempt test transplant.
- Harness stores before-fix test result.
- Reproduced bug is reported as `MASTER_REPRODUCED_ON_015`.
- Failed transplant becomes `INCONCLUSIVE`, not discarded.

---

## 22. Milestone 20: fix verification support

This is the highest-confidence phase.

### Tasks for Codex

- Apply or adapt production fix to OSS `0.15`.
- Run the same focused test again.
- Capture logs.
- Save adapted patch.
- Return result.

### Harness tasks

- Validate patch path.
- Validate after-fix test passed.
- Store patch path and logs.
- Upgrade decision to `MASTER_FIX_VERIFIED_ON_015`.

### Acceptance criteria

- Test fails before fix.
- Adapted fix is applied.
- Test passes after fix.
- Patch is saved.
- Report shows very high confidence.

---

## 23. Milestone 21: tests

### Unit tests

Add tests for:

- Date parsing.
- Scan filters.
- PR upsert idempotency.
- Queue state transitions.
- Priority assignment.
- Result schema validation.
- Decision-specific validation.
- Report generation.
- Stale recovery.

### Integration tests

Add tests with mocked GitHub API:

- Scan one branch.
- Scan both branches.
- Re-scan same range.
- Store changed files.
- List PRs.
- Analyze dry run.

### Optional end-to-end test

Use a small local fake git repo and fake Codex command that writes `codex_result.json`.

Acceptance criteria:

- CI can run tests without real Codex.
- CI can run tests without GitHub token.
- Critical state transitions are covered.

---

## 24. Milestone 22: documentation

### README sections

- Purpose.
- Security boundary.
- Setup.
- Config.
- GitHub token.
- Common workflows.
- Historical catch-up.
- Listing PRs.
- Limited analysis.
- Retry.
- Recover stale runs.
- Reports.
- Human review.
- Troubleshooting.

### Example workflow

```bash
backport-harness db init

backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31

backport-harness list-prs --branch 0.15 --limit 20

backport-harness analyze --branch 0.15 --limit 5 --dry-run

backport-harness analyze --branch 0.15 --limit 5

backport-harness report

backport-harness review --pr 12345 --status accepted_for_backport
```

### Acceptance criteria

- New engineer can run scanner.
- New engineer can list saved PRs.
- New engineer can analyze a small batch.
- New engineer can regenerate reports.

---

## 25. MVP acceptance criteria

MVP is complete when:

1. `scan --from-date [--to-date]` works.
2. Scanning is slow/rate-limit-aware.
3. PRs and changed files are stored idempotently.
4. `list-prs` works.
5. `inspect --pr` works.
6. `analyze --dry-run` works.
7. Codex can be invoked for one PR.
8. Codex has a 2-hour timeout.
9. Stale Codex runs can be recovered.
10. Codex result JSON is validated.
11. Decisions and evidence are stored in SQLite.
12. Reports are generated.
13. System can be stopped and continued later.
14. No private repo access is required.

---

## 26. Suggested first development sprint

### Sprint goal

Build a useful scanner and reviewable queue without full test transplantation.

### Scope

- Project skeleton.
- DB schema.
- Config.
- GitHub scanner.
- List PRs.
- Inspect PR.
- Analysis queue.
- Dry-run analysis.
- Basic Codex invocation.
- Basic result validation.
- Report generation.

### Out of scope for first sprint

- Test transplantation.
- Fix verification.
- Advanced retry policy.
- Scan pagination checkpointing.
- Full human review lifecycle.

### Sprint acceptance demo

Run:

```bash
backport-harness scan --from-date 2024-01-01 --to-date 2024-02-01
backport-harness list-prs
backport-harness inspect --pr 12345
backport-harness analyze --limit 3 --dry-run
backport-harness analyze --limit 1
backport-harness report
```

Expected result:

- SQLite contains scanned PRs.
- One PR is analyzed by Codex.
- `backport-candidates.md`, `inconclusive.md`, and `discarded.jsonl` are generated.

---

## 27. Important implementation notes

### Do not over-optimize scanner checkpointing in MVP

Because scanning is idempotent and cheaper than Codex, it is acceptable to rerun scans from the same date range.

Add true pagination checkpoints later if needed.

### Do not require test transplantation in MVP

Test transplantation is valuable but brittle. The first useful system should classify and prioritize candidates.

### Prefer `INCONCLUSIVE` over unsafe discard

Unsafe discard is the biggest risk. A false positive costs review time. A false discard loses a real bugfix.

### Store raw Codex output

Always save:

- stdout
- stderr
- `codex_result.json`
- `notes.md`
- logs
- patches

This makes debugging possible.

### Keep reports generated from DB

Reports should be reproducible without rerunning Codex.

### Codex prompt must repeat the security boundary

Every prompt should explicitly state:

```text
Do not use or request private fork access.
Use only the provided public upstream repository and public OSS 0.15 worktree.
```

---

## 28. Final target workflow

```bash
# 1. Initialize
backport-harness db init

# 2. Historical catch-up scan
backport-harness scan --from-date 2024-01-01 --to-date 2024-12-31

# 3. Look at saved PRs
backport-harness list-prs --limit 100
backport-harness list-prs --branch 0.15
backport-harness list-prs --branch master

# 4. Analyze a small batch because Codex limits are strict
backport-harness analyze --limit 5 --dry-run
backport-harness analyze --limit 5

# 5. Recover stale runs if interrupted
backport-harness recover-stale

# 6. Retry failed cases later
backport-harness retry --status FAILED_INFRA --limit 3

# 7. Generate reports
backport-harness report

# 8. Human review
backport-harness review --pr 12345 --status accepted_for_backport
```
