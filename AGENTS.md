# Development Rules for Agents

This repository is developed task by task. Agents must follow these rules before changing code, docs, configuration, or project structure.

## Core Workflow

1. Start every new unit of work from a task file in `docs/tasks/`.
2. Write or update the task specification in Markdown before implementation.
3. Check the task specification against the project documentation before coding:
   - `docs/backport_harness_design.md`
   - `docs/backport_harness_implementation_steps.md`
   - any relevant active task files in `docs/tasks/`
   - any relevant archived task files in `docs/archive/tasks/`
4. Resolve conflicts or contradictions between the task and documentation before implementation.
5. Implement only the scope described by the task file.
6. Run the relevant tests and checks before considering the task complete.
7. Record any test failures, skipped checks, or unresolved risks in the final response.

## Task Files

- Task files live in `docs/tasks/`.
- Completed task files may be moved to `docs/archive/tasks/` after their work
  has landed.
- Use numeric prefixes to preserve ordering, for example:

  ```text
  docs/tasks/001-foundation.md
  docs/tasks/002-sqlite-schema.md
  docs/tasks/003-github-scanner.md
  ```

- A task file must include:
  - goal
  - implementation scope
  - expected behavior
  - affected modules or commands
  - test plan
  - assumptions and explicit non-goals

- If a task is too large, split it into smaller task files before coding.
- Do not implement undocumented behavior just because it seems useful.

## Documentation Alignment

Before implementation, compare the task with the design docs.

If the task conflicts with existing documentation:

- stop implementation work
- update the task or documentation first
- make the conflict explicit
- proceed only once the intended behavior is clear

The design docs are the source of product intent. Task files are the source of implementation scope for the current unit of work.

## Branch and Pull Request Policy

All development should happen on a separate branch per task.

Branch naming convention:

```text
task/<task-number>-<short-name>
```

Examples:

```text
task/001-foundation
task/002-sqlite-schema
task/003-github-scanner
```

Do not implement task work directly on `main`.

After implementation:

1. commit the task changes
2. push the task branch
3. create a GitHub pull request
4. include the task file path in the PR description
5. summarize tests run and known risks in the PR description

If GitHub access or push permissions are unavailable, leave the branch and commit ready locally and report exactly what remains.

## Git Hygiene

- Inspect `git status` before editing.
- Do not overwrite unrelated user changes.
- Do not revert changes you did not make unless explicitly asked.
- If existing local changes overlap with the task, understand them before editing.
- If conflicts make the task ambiguous, stop and ask for direction.
- Avoid unrelated refactors, formatting churn, or dependency changes.

## Implementation Rules

- Prefer existing project patterns over new abstractions.
- Keep changes narrowly scoped to the active task.
- Add tests proportional to risk and behavior changed.
- Keep deterministic Python orchestration as the source of truth.
- Do not let Codex or any agent output become trusted without validation.
- Preserve the project security boundary: never access private forks, private patches, private repository history, or private test results.

## Verification

Run the smallest meaningful test set for the task, then broader checks when the task affects shared behavior.

Expected verification examples:

```sh
pytest
pytest tests/test_config.py
pytest tests/test_codex_runner.py
```

When CLI behavior is changed, also run the relevant command manually with safe local/test inputs.

Do not claim a task is complete unless verification has been run or the reason it could not be run is clearly documented.

## Final Response Requirements

When reporting completed work, include:

- task file used
- branch name, if created
- files changed
- tests/checks run
- any remaining risks or follow-ups

Keep the summary concise and factual.
