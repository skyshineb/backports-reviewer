# Local Commit Dashboard

## Start the service

```sh
.venv/bin/backport-harness serve --fork-root /path/containing/your/fork
```

Open the URL printed in the terminal. Its fragment grants access to this
session and stays in the browser. The service binds to `127.0.0.1` and uses
port 8765 by default. Use `--port` to select another port. Repeat
`--fork-root` if the operator needs access to multiple approved directories.
The default approved root is `workspace/forks`.

The dashboard uses the PR CLI's configured SQLite location by default. Use
`--database` to select a different SQLite file and `--state-dir` to choose where
to keep the Git mirror and worktrees. Keep the state local to the operator.
The mirror holds Git objects for the configured private fork and the database
contains prompts, diffs, and notes.

## Choose Codex authentication

To use the local Codex CLI with your ChatGPT account, run these commands as the
same OS user that runs the dashboard:

```sh
codex login status
codex login  # only if a ChatGPT session is needed
.venv/bin/backport-harness serve --codex-backend cli --fork-root /path/containing/your/fork
```

The CLI backend reuses the saved ChatGPT session and uses the account's default
model at high reasoning effort, or the model chosen by `--codex-model`.
It accepts CLI versions that support the restricted permission profile,
output schema, and `--ignore-user-config`. Login and job execution use the
local Codex binary. The harness supplies two read-only snapshot tools and
validates the resulting JSON.

The default `--codex-backend api` uses the OpenAI Responses API. Set
`OPENAI_API_KEY` in the service process environment to activate it. Its
default model is `gpt-6.2-astra` at high reasoning effort. `--codex-model`
can select a model that supports Responses tools and structured outputs.

The selected provider receives the upstream diff, operator guidance, and
selected text from the pinned fork snapshot. Set a limit of zero in settings
to use manual analysis exclusively.

## Review and apply

1. Open **Настройки** and save the upstream slug and branch, the base release
   tag or SHA, the local fork path and target branch. The default upstream is
   `lance-format/lance` on `main`.
2. Browse **Журнал**. The subject opens details, agent notes and attempts.
   **Analyze** opens the operator prompt. **Skip** records the operator's
   decision and can be undone from the row.
3. Use **Apply** for a clean patch. When the patch conflicts, edit the prompt
   and inspect the proposed diff before confirming the write. If the target
   changes, prepare a new diff. For direct writes, use a dedicated target
   branch that is free of user worktrees.
4. Use **Очередь** to run a scan, pause or resume automatic processing, retry
   a failed job, cancel a pending write, or inspect attempts. After an upstream
   rewrite, use **Обход от базы** to establish the new cursor. Use the same
   action to revisit the original range after changing title words.

Each Git probe, review and patch is tied to a fork SHA. The dashboard marks
earlier checks when the branch advances. An Apply always checks the current
target again. Confirmations refer to the prepared commit and expected HEAD.

## Verification

```sh
.venv/bin/python -m pytest tests/test_dashboard_git.py tests/test_dashboard_worker.py tests/test_dashboard_web.py
.venv/bin/python -m pytest
.venv/bin/backport-harness serve --help
```

The workflow and HTTP tests use temporary upstream and fork repositories and
a fake Codex provider. HTTP verification needs local loopback sockets.
