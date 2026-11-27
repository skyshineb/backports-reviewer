from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from backport_harness.dashboard.models import ProfileSettings, ScanBatch, SourceCommit


class GitError(RuntimeError):
    pass


class UpstreamRewrite(GitError):
    pass


def git(
    cwd: Path,
    *arguments: str,
    allowed: tuple[int, ...] = (0,),
    data: bytes | None = None,
    local_transport: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    env = {
        "PATH": os.defpath if "PATH" not in os.environ else os.environ["PATH"],
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    command = [
        "git", "-C", str(cwd),
        "-c", f"core.hooksPath={os.devnull}",
        "-c", "core.fsmonitor=false",
        "-c", "rerere.enabled=false",
        "-c", "commit.gpgSign=false",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", f"protocol.file.allow={'always' if local_transport else 'never'}",
        "-c", "http.followRedirects=false",
        *arguments,
    ]
    try:
        result = subprocess.run(command, input=data, capture_output=True, env=env, timeout=180)
    except subprocess.TimeoutExpired as error:
        raise GitError(f"Git {arguments[0]} timed out.") from error
    if result.returncode not in allowed:
        error = result.stderr.decode("utf-8", "replace").strip()[-1500:]
        raise GitError(f"Git {arguments[0]} failed ({result.returncode}). {error}".strip())
    return result


def output(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stdout.decode("utf-8", "replace").strip()


def resolve_commit(repo: Path, ref: str) -> str:
    return output(git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"))


def branch_ref(branch: str) -> str:
    return "refs/heads/" + branch.removeprefix("refs/heads/")


def base_ref(ref: str) -> str:
    if re.fullmatch(r"[a-fA-F0-9]{7,64}", ref):
        return ref.lower()
    return "refs/tags/" + ref.removeprefix("refs/tags/")


class GitWorkspace:
    def __init__(
        self,
        root: Path,
        fork_roots: list[Path],
        upstream_url: Callable[[str], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fork_roots = [path.resolve() for path in fork_roots]
        self.upstream_url = upstream_url
        self._init_lock = threading.Lock()

    def _allow(self, path: Path) -> None:
        if not any(path.is_relative_to(root) for root in self.fork_roots):
            raise ValueError("The fork and its Git directory must be within an approved fork root.")
        if path.is_relative_to(self.root):
            raise ValueError("Select a fork outside the dashboard state directory.")

    def fork(self, path: Path) -> Path:
        fork = path.expanduser().resolve(strict=True)
        self._allow(fork)
        if not fork.is_dir():
            raise ValueError("Select a directory containing the local fork.")
        metadata = output(git(fork, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        self._allow(Path(metadata).resolve(strict=True))
        bare = output(git(fork, "rev-parse", "--is-bare-repository")) == "true"
        if not bare and output(git(fork, "rev-parse", "--is-inside-work-tree")) != "true":
            raise ValueError("Select the root directory of the local fork.")
        root = Path(metadata if bare else output(git(fork, "rev-parse", "--show-toplevel")))
        if root.resolve() != fork:
            raise ValueError("Select the root directory of the local fork.")
        return fork

    def validate(self, settings: ProfileSettings) -> ProfileSettings:
        fork = self.fork(settings.fork_path)
        upstream = branch_ref(settings.upstream_branch)
        target = branch_ref(settings.target_branch)
        for ref in (upstream, target, base_ref(settings.base_ref)):
            if ref.startswith("refs/"):
                git(self.root, "check-ref-format", ref)
        resolve_commit(fork, target)
        return settings.model_copy(update={
            "fork_path": fork,
            "upstream_branch": upstream.removeprefix("refs/heads/"),
            "target_branch": target.removeprefix("refs/heads/"),
            "base_ref": base_ref(settings.base_ref),
        })

    def mirror(self, profile_id: int) -> Path:
        profile_dir = self.root / str(profile_id)
        mirror = profile_dir / "mirror.git"
        with self._init_lock:
            if not (mirror / "HEAD").exists():
                profile_dir.mkdir(mode=0o700, exist_ok=True)
                git(profile_dir, "init", "--bare", "--template=", str(mirror))
        return mirror

    def scan(
        self,
        profile_id: int,
        settings: ProfileSettings,
        cursor: str | None,
        saved_base: str | None,
    ) -> ScanBatch:
        mirror = self.mirror(profile_id)
        url = (
            self.upstream_url(settings.upstream)
            if self.upstream_url is not None
            else f"https://github.com/{settings.upstream}.git"
        )
        source_ref = branch_ref(settings.upstream_branch)
        refspecs = [f"+{source_ref}:refs/backports-reviewer/upstream"]
        initial_ref = base_ref(settings.base_ref)
        if saved_base is None and initial_ref.startswith("refs/tags/"):
            refspecs.append(f"+{initial_ref}:refs/backports-reviewer/base")
            initial_ref = "refs/backports-reviewer/base"
        git(
            mirror, "fetch", "--atomic", "--no-tags", "--no-write-fetch-head",
            "--no-auto-maintenance", "--no-recurse-submodules", url, *refspecs,
            local_transport=self.upstream_url is not None,
        )
        head = resolve_commit(mirror, "refs/backports-reviewer/upstream")
        base = saved_base or resolve_commit(mirror, initial_ref)
        if git(mirror, "merge-base", base, head, allowed=(0, 1)).returncode:
            if cursor:
                raise UpstreamRewrite("Upstream no longer shares history with the saved base.")
            raise GitError("The configured base and upstream branch do not share Git history.")

        raw = git(
            mirror, "log", "--first-parent", "--reverse", "-z",
            "--format=%H%x00%P%x00%cI%x00%s%x00%b", f"{cursor or base}..{head}",
        ).stdout
        found = parse_log(raw)
        if cursor and head != cursor and (not found or found[0].parents[:1] != (cursor,)):
            raise UpstreamRewrite("Upstream first-parent history changed. Rescan from the base.")

        words = "|".join(re.escape(term) for term in settings.match_words.split())
        title_pattern = re.compile(rf"(?<![a-z0-9])(?:{words})(?![a-z0-9])", re.IGNORECASE)
        # Preserve source objects for existing reviews when upstream rewrites its history.
        git(mirror, "update-ref", f"refs/backports-reviewer/scans/{head}", head)
        return ScanBatch(head, base, [commit for commit in found if title_pattern.search(commit.subject)])

    def snapshot(self, profile_id: int, settings: ProfileSettings) -> str:
        fork = self.fork(settings.fork_path)
        mirror = self.mirror(profile_id)
        ref = branch_ref(settings.target_branch)
        git(
            mirror, "fetch", "--no-tags", "--no-write-fetch-head",
            "--no-auto-maintenance", "--no-recurse-submodules",
            str(fork), f"+{ref}:refs/backports-reviewer/fork",
            local_transport=True,
        )
        return resolve_commit(mirror, "refs/backports-reviewer/fork")

    @contextmanager
    def worktree(self, profile_id: int, sha: str) -> Iterator[Path]:
        mirror = self.mirror(profile_id)
        with tempfile.TemporaryDirectory(prefix="worktree-", dir=mirror.parent) as directory:
            tree = Path(directory) / "checkout"
            git(mirror, "worktree", "add", "--detach", str(tree), sha)
            try:
                yield tree
            finally:
                git(mirror, "worktree", "remove", "--force", str(tree))

    def probe(self, profile_id: int, target: str, source: str, parent_count: int) -> str:
        with self.worktree(profile_id, target) as tree:
            return cherry_pick(tree, source, parent_count)


def parse_log(raw: bytes) -> list[SourceCommit]:
    if not raw:
        return []
    fields = raw.removesuffix(b"\0").decode("utf-8", "replace").split("\0")
    if len(fields) % 5:
        raise GitError("Git returned an incomplete commit record.")
    return [
        SourceCommit(sha, tuple(parents.split()), date, subject, body.rstrip())
        for sha, parents, date, subject, body in zip(
            fields[0::5], fields[1::5], fields[2::5], fields[3::5], fields[4::5], strict=True
        )
    ]


def cherry_pick(tree: Path, source: str, parent_count: int) -> str:
    mainline = ("--mainline", "1") if parent_count > 1 else ()
    result = git(tree, "cherry-pick", "--no-commit", *mainline, source, allowed=(0, 1, 128))
    if result.returncode and git(tree, "ls-files", "--unmerged", "-z").stdout:
        return "conflict"
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace").strip()[-1500:]
        raise GitError(f"Cherry-pick failed. {error}")
    changed = git(tree, "diff", "--cached", "--quiet", "--no-ext-diff", allowed=(0, 1))
    return "applicable" if changed.returncode else "empty"
