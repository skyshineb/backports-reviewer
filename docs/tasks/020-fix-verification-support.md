# Fix Verification Support

## Goal

Support Codex-driven adapted fix verification on public OSS `0.15` and store high-confidence evidence.

## Implementation Scope

- Expand prompt guidance for Codex-driven adapted fix verification in public OSS `0.15`.
- Keep `schema_version: 1` and the existing result fields:
  - `test_transplant`
  - `test_before_fix`
  - `fix_verification`
- Harden result validation for verified-fix outcomes.
- Persist adapted patch evidence in SQLite so reports and inspection do not rely on temporary Codex output.
- Store validated after-fix verification attempts in `test_runs`.
- Add focused tests for verified-fix prompting, validation, storage, inspection, and reports.

## Expected Behavior

- Test fails before fix.
- Adapted fix is applied in the public worktree.
- Test passes after fix.
- Patch and logs are saved.
- Report can show `MASTER_FIX_VERIFIED_ON_015` with `very_high` confidence.
- `full-audit.jsonl` and `inspect` expose stored adapted patch evidence.

## Affected Modules or Commands

- `docs/tasks/020-fix-verification-support.md`
- Prompt templates
- Result validator
- Decision/test storage
- SQLite migrations
- Inspect output
- Report writer

## Test Plan

- Cover prompt guidance for adapted public OSS `0.15` patch generation, after-fix test logs, `test_pass` evidence, and `very_high` confidence.
- Cover result validation for:
  - valid verified fix
  - missing patch
  - missing after-fix log
  - passing test without before-fix failure
  - failed after-fix test
  - missing `test_pass` evidence
  - verified fix without `very_high` confidence
- Cover storage of evidence `patch_path` and after-fix `fix_verification` test attempts.
- Cover inspect and report output for stored adapted patch evidence.
- Run `pytest tests/test_prompt_templates.py`.
- Run `pytest tests/test_codex_result.py`.
- Run `pytest tests/test_result_validator.py`.
- Run `pytest tests/test_storage.py tests/test_report_writer.py`.
- Run full `pytest`.

## Assumptions and Explicit Non-goals

- This task has been checked against `docs/backport_harness_design.md`, `docs/backport_harness_implementation_steps.md`, tasks 012, 013, 014, 015, and 019.
- Do not change the Codex result schema version.
- Do not add a new CLI command; fix verification remains part of Codex analysis.
- This milestone never applies fixes to the private fork.
- Do not access private forks, private patches, private repository history, private test results, or private paths.
