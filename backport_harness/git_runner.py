from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitResult:
    args: list[str]
    stdout: str
    stderr: str


class GitCommandError(RuntimeError):
    def __init__(
        self,
        args: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.args_list = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            "Git command failed "
            f"(exit {returncode}): {' '.join(args)}\n"
            f"stdout: {stdout.strip() or '-'}\n"
            f"stderr: {stderr.strip() or '-'}"
        )


def run_git(args: list[str], *, cwd: Path | None = None) -> GitResult:
    if not args or args[0] != "git":
        raise ValueError("Git command args must start with 'git'.")

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise GitCommandError(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return GitResult(
        args=args,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
