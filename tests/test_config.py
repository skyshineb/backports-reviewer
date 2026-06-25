from pathlib import Path

import pytest

from backport_harness.config import (
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_CODEX_TIMEOUT_SECONDS,
    DEFAULT_STALE_TIMEOUT_SECONDS,
    DEFAULT_TARGET_LABEL,
    DEFAULT_TARGET_REF,
    DEFAULT_TARGET_WORKTREE_SUFFIX,
    load_config,
)


def write_config(path: Path, extra: str = "") -> None:
    path.write_text(
        f"""
github:
  owner: apache
  repo: hudi
  branches:
    - master
    - "0.15"
  token_env: GITHUB_TOKEN

local_repo:
  upstream_url: https://github.com/apache/hudi.git
  repo_dir: ./workspace/upstream
  worktree_dir: ./workspace/worktrees
  target_ref:
    label: "0.15"
    ref: origin/release-0.15.0
    worktree_suffix: "015"

codex:
  command: codex
  mode: exec
  max_attempts_per_pr: 2
  result_file: output/codex_result.json

reports:
  output_dir: ./reports

storage:
  sqlite_path: ./workspace/backport_harness.sqlite3
{extra}
""".lstrip(),
        encoding="utf-8",
    )


def test_load_config_returns_typed_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    config = load_config(config_path)

    assert config.github.owner == "apache"
    assert config.github.repo == "hudi"
    assert config.github.branches == ["master", "0.15"]
    assert config.local_repo.upstream_url == "https://github.com/apache/hudi.git"
    assert config.local_repo.target_ref.label == DEFAULT_TARGET_LABEL
    assert config.local_repo.target_ref.ref == DEFAULT_TARGET_REF
    assert config.local_repo.target_ref.worktree_suffix == DEFAULT_TARGET_WORKTREE_SUFFIX


def test_load_config_reads_custom_target_ref(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
github:
  owner: lance-format
  repo: lance
  branches:
    - main
  token_env: GITHUB_TOKEN

local_repo:
  upstream_url: https://github.com/lance-format/lance.git
  repo_dir: ./workspace/lance/upstream
  worktree_dir: ./workspace/lance/worktrees
  target_ref:
    label: v7.0.0
    ref: refs/tags/v7.0.0
    worktree_suffix: v7.0.0

codex:
  command: codex
  mode: exec
  max_attempts_per_pr: 2
  result_file: output/codex_result.json

reports:
  output_dir: ./reports

storage:
  sqlite_path: ./workspace/backport_harness.sqlite3
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.local_repo.target_ref.label == "v7.0.0"
    assert config.local_repo.target_ref.ref == "refs/tags/v7.0.0"
    assert config.local_repo.target_ref.worktree_suffix == "v7.0.0"


def test_load_config_rejects_unsafe_target_ref_worktree_suffix(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
github:
  owner: lance-format
  repo: lance
  branches:
    - main
  token_env: GITHUB_TOKEN

local_repo:
  upstream_url: https://github.com/lance-format/lance.git
  repo_dir: ./workspace/lance/upstream
  worktree_dir: ./workspace/lance/worktrees
  target_ref:
    label: unsafe
    ref: refs/tags/unsafe
    worktree_suffix: ../unsafe

codex:
  command: codex
  mode: exec
  max_attempts_per_pr: 2
  result_file: output/codex_result.json

reports:
  output_dir: ./reports

storage:
  sqlite_path: ./workspace/backport_harness.sqlite3
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="safe path segment"):
        load_config(config_path)


def test_load_config_applies_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path)

    config = load_config(config_path)

    assert config.codex.timeout_seconds == DEFAULT_CODEX_TIMEOUT_SECONDS
    assert config.codex.reasoning_effort == DEFAULT_CODEX_REASONING_EFFORT
    assert config.analysis.default_limit == 5
    assert config.analysis.stale_timeout_seconds == DEFAULT_STALE_TIMEOUT_SECONDS


def test_load_config_reads_custom_codex_reasoning_effort(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  result_file: output/codex_result.json\n",
            "  result_file: output/codex_result.json\n  reasoning_effort: high\n",
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.codex.reasoning_effort == "high"


def test_load_config_rejects_invalid_codex_reasoning_effort(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  result_file: output/codex_result.json\n",
            "  result_file: output/codex_result.json\n  reasoning_effort: maximum\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="codex.reasoning_effort"):
        load_config(config_path)


def test_load_config_reads_github_token_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")

    config = load_config(config_path)

    assert config.github.token == "from-env"


def test_load_config_rejects_embedded_github_token(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
github:
  owner: apache
  repo: hudi
  branches:
    - master
  token_env: GITHUB_TOKEN
  token: embedded-token
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not embed a token"):
        load_config(config_path)


def test_load_config_resolves_relative_paths_from_config_file(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "nested" / "config.yaml"
    config_path.parent.mkdir()
    write_config(config_path)

    config = load_config(config_path)

    assert config.local_repo.repo_dir == tmp_path / "nested" / "workspace" / "upstream"
    assert config.local_repo.worktree_dir == (
        tmp_path / "nested" / "workspace" / "worktrees"
    )
    assert config.reports.output_dir == tmp_path / "nested" / "reports"
    assert config.storage.sqlite_path == (
        tmp_path / "nested" / "workspace" / "backport_harness.sqlite3"
    )


def test_load_config_rejects_forbidden_private_path_overlap(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        extra="""
security:
  forbidden_private_prefixes:
    - ./workspace
""",
    )

    with pytest.raises(ValueError, match="forbidden private prefix"):
        load_config(config_path)


def test_load_config_rejects_missing_required_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
github:
  owner: apache
  branches:
    - master
  token_env: GITHUB_TOKEN
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="github.repo"):
        load_config(config_path)
