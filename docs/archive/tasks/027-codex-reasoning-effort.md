# Codex Reasoning Effort

## Goal

Make Codex reasoning effort explicit for harness analysis runs so future
`backport-harness analyze` invocations use `medium` by default instead of
inheriting the operator's user-level Codex config.

## Implementation Scope

- Add `codex.reasoning_effort` to the typed harness config.
- Default `codex.reasoning_effort` to `medium`.
- Validate allowed values: `low`, `medium`, `high`, and `xhigh`.
- Pass the configured value from `analysis_runner` to `codex_runner`.
- Invoke `codex exec` with an explicit `model_reasoning_effort` config override.
- Set `reasoning_effort: medium` in `config.yaml` and `config.lance-v7.yaml`.
- Update relevant usage/design task documentation and tests.

## Expected Behavior

- Existing configs that omit `codex.reasoning_effort` run Codex with
  `model_reasoning_effort="medium"`.
- Configs can opt into `low`, `high`, or `xhigh`.
- Invalid reasoning effort values fail during config loading.
- GitHub token stripping, timeout handling, logs, result validation, queue
  state transitions, and reports remain unchanged.

## Affected Modules or Commands

- `backport_harness/config.py`
- `backport_harness/analysis_runner.py`
- `backport_harness/codex_runner.py`
- `config.yaml`
- `config.lance-v7.yaml`
- `docs/usage.md`
- `docs/backport_harness_implementation_steps.md`
- `docs/tasks/011-codex-runner.md`
- focused tests for config, Codex runner argv, and analysis flow request wiring

## Test Plan

- Run focused tests:
  - `.venv/bin/python -m pytest tests/test_config.py tests/test_codex_runner.py tests/test_analysis_runner.py`
- Run full test suite:
  - `.venv/bin/python -m pytest`

## Assumptions and Explicit Non-goals

- This applies to all future harness Codex runs by default, not only Lance.
- Existing stored analysis results are not rerun or rewritten.
- This task does not change model selection, PR queue ordering, result
  validation, retry behavior, report generation, or Codex provider credentials.

## Execution Journal

- Created branch `task/027-codex-reasoning-effort` from
  `task/026-lance-v7-harness-run`.
- Compared this task with the Codex runner task, implementation-step docs, and
  usage docs before implementation.
- Added `codex.reasoning_effort` with default `medium` and validation for
  `low`, `medium`, `high`, and `xhigh`.
- Updated Codex invocation to pass
  `-c model_reasoning_effort="<configured-effort>"`.
- Set `reasoning_effort: medium` in `config.yaml` and
  `config.lance-v7.yaml`.
- Updated docs and focused tests for config loading, Codex argv construction,
  and analysis-runner propagation.
- Ran focused tests:
  `.venv/bin/python -m pytest tests/test_config.py tests/test_codex_runner.py tests/test_analysis_runner.py`;
  20 passed.
- Ran full test suite: `.venv/bin/python -m pytest`; 275 passed.
- Ran Lance dry-run config check:
  `.venv/bin/backport-harness --config config.lance-v7.yaml analyze --dry-run --limit 1`;
  selected #6989 without mutating the queue.
