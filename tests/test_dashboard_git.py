from pathlib import Path

import pytest

from backport_harness.dashboard.git import GitError, GitWorkspace, UpstreamRewrite, git, resolve_commit
from backport_harness.dashboard.models import ProfileSettings
from backport_harness.dashboard.store import DashboardStore


def commit(repository: Path, name: str, text: str, subject: str) -> str:
    (repository / name).write_text(text, encoding="utf-8")
    git(repository, "add", "--", name)
    git(repository, "-c", "user.name=Test", "-c", "user.email=test@example.test",
        "commit", "-m", subject)
    return resolve_commit(repository, "HEAD")


@pytest.fixture
def repositories(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-b", "main")
    base = commit(upstream, "conflict.txt", "base\n", "Base")
    git(upstream, "tag", "v1", base)
    fork = tmp_path / "fork"
    git(tmp_path, "clone", str(upstream), str(fork), local_transport=True)
    git(fork, "switch", "-c", "target")
    commit(fork, "conflict.txt", "private behavior\n", "Fork changes")
    git(fork, "switch", "main")
    workspace = GitWorkspace(tmp_path / "git-state", [tmp_path], lambda _slug: str(upstream))
    settings = workspace.validate(ProfileSettings(
        base_ref="v1", fork_path=fork, target_branch="target"
    ))
    return upstream, fork, workspace, settings, base


def test_incremental_first_parent_scan_and_migration(tmp_path, repositories):
    upstream, _, workspace, settings, base = repositories
    fixes = [
        commit(upstream, "file.txt", "fix 1\n", "Fix parser"),
        commit(upstream, "file.txt", "fix 2\n", "Bug: error path"),
    ]
    git(upstream, "switch", "-c", "feature")
    commit(upstream, "side.txt", "side fix\n", "Fix side-only issue")
    git(upstream, "switch", "main")
    git(upstream, "-c", "user.name=Test", "-c", "user.email=test@example.test",
        "merge", "--no-ff", "-m", "Fix on merge", "feature")
    merge = resolve_commit(upstream, "HEAD")
    store = DashboardStore(tmp_path / "state.sqlite3")
    profile = store.save_profile(settings)
    batch = workspace.scan(profile, settings, None, None)

    assert batch.base == base
    assert batch.head == merge
    assert [item.sha for item in batch.commits] == [*fixes, merge]
    assert len(batch.commits[-1].parents) == 2
    with store.transaction(write=True) as db:
        assert store.save_scan(db, profile, batch) == 3
        assert store.save_scan(db, profile, batch) == 0
        assert db.execute("SELECT count(*) FROM dashboard_jobs").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM prs").fetchone()[0] == 0
    assert store.active_profile()["cursor"] == merge

    commit(upstream, "other.txt", "unrelated\n", "Update fixture")
    next_fix = commit(upstream, "other.txt", "fixed\n", "fix(other): improve handling")
    next_batch = workspace.scan(profile, settings, merge, base)
    assert [item.sha for item in next_batch.commits] == [next_fix]
    git(upstream, "reset", "--hard", base)
    replacement = commit(upstream, "other.txt", "replacement\n", "Bugfix: rewrite")
    with pytest.raises(UpstreamRewrite):
        workspace.scan(profile, settings, next_fix, base)
    assert workspace.scan(profile, settings, None, base).head == replacement
    assert resolve_commit(workspace.mirror(profile), merge) == merge


def test_worktree_probe_outcomes(repositories):
    upstream, fork, workspace, settings, _ = repositories
    clean = commit(upstream, "clean.txt", "fixed\n", "Fix clean candidate")
    conflict = commit(upstream, "conflict.txt", "upstream behavior\n", "Fix conflict")
    workspace.scan(1, settings, None, None)
    target = workspace.snapshot(1, settings)

    assert workspace.probe(1, target, clean, 1) == "applicable"
    assert workspace.probe(1, target, conflict, 1) == "conflict"
    assert workspace.probe(1, clean, clean, 1) == "empty"
    with pytest.raises(GitError):
        workspace.probe(1, target, "9999999", 1)
    assert resolve_commit(fork, "refs/heads/target") == target
    assert not list(workspace.mirror(1).parent.glob("worktree-*"))


def test_fork_roots_and_git_directory_are_validated(tmp_path, repositories):
    _, fork, _, settings, _ = repositories
    workspace = GitWorkspace(tmp_path / "isolated", [tmp_path / "approved"])
    with pytest.raises(ValueError, match="approved fork root"):
        workspace.validate(settings)
    workspace = GitWorkspace(tmp_path / "isolated", [fork])
    with pytest.raises(ValueError, match="root directory"):
        workspace.fork(fork / ".git")
