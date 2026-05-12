from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CODEX_TIMEOUT_SECONDS = 7200
DEFAULT_STALE_TIMEOUT_SECONDS = 7200
DEFAULT_REQUEST_DELAY_SECONDS = 1.0
DEFAULT_PAGE_DELAY_SECONDS = 2.0
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_RESPECT_RATE_LIMIT = True
DEFAULT_ANALYSIS_LIMIT = 5

TOKEN_FIELD_NAMES = {"token", "github_token", "access_token"}


@dataclass(frozen=True)
class GithubConfig:
    owner: str
    repo: str
    branches: list[str]
    token_env: str
    token: str | None
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS
    page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER
    respect_rate_limit: bool = DEFAULT_RESPECT_RATE_LIMIT


@dataclass(frozen=True)
class LocalRepoConfig:
    upstream_url: str
    repo_dir: Path
    worktree_dir: Path


@dataclass(frozen=True)
class CodexConfig:
    command: str
    mode: str
    timeout_seconds: int
    max_attempts_per_pr: int
    result_file: str


@dataclass(frozen=True)
class AnalysisConfig:
    default_limit: int
    stale_timeout_seconds: int


@dataclass(frozen=True)
class ReportsConfig:
    output_dir: Path


@dataclass(frozen=True)
class StorageConfig:
    sqlite_path: Path


@dataclass(frozen=True)
class SecurityConfig:
    forbidden_private_prefixes: list[Path]
    task_dir: Path | None = None


@dataclass(frozen=True)
class HarnessConfig:
    github: GithubConfig
    local_repo: LocalRepoConfig
    codex: CodexConfig
    analysis: AnalysisConfig
    reports: ReportsConfig
    storage: StorageConfig
    security: SecurityConfig


def load_config(path: str | Path) -> HarnessConfig:
    """Load, normalize, and validate the harness YAML config."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping.")

    _reject_embedded_tokens(data, "config")
    base_dir = config_path.parent.resolve()
    config = HarnessConfig(
        github=_load_github_config(data),
        local_repo=_load_local_repo_config(data, base_dir),
        codex=_load_codex_config(data),
        analysis=_load_analysis_config(data),
        reports=_load_reports_config(data, base_dir),
        storage=_load_storage_config(data, base_dir),
        security=_load_security_config(data, base_dir),
    )
    _validate_forbidden_path_overlaps(config)
    return config


def _load_github_config(data: dict[str, Any]) -> GithubConfig:
    section = _required_mapping(data, "github")
    token_env = _required_str(section, "token_env", "github")

    return GithubConfig(
        owner=_required_str(section, "owner", "github"),
        repo=_required_str(section, "repo", "github"),
        branches=_required_str_list(section, "branches", "github"),
        token_env=token_env,
        token=os.environ.get(token_env),
        request_delay_seconds=_optional_float(
            section,
            "request_delay_seconds",
            DEFAULT_REQUEST_DELAY_SECONDS,
            "github",
        ),
        page_delay_seconds=_optional_float(
            section,
            "page_delay_seconds",
            DEFAULT_PAGE_DELAY_SECONDS,
            "github",
        ),
        max_retries=_optional_int(section, "max_retries", DEFAULT_MAX_RETRIES, "github"),
        backoff_multiplier=_optional_float(
            section,
            "backoff_multiplier",
            DEFAULT_BACKOFF_MULTIPLIER,
            "github",
        ),
        respect_rate_limit=_optional_bool(
            section,
            "respect_rate_limit",
            DEFAULT_RESPECT_RATE_LIMIT,
            "github",
        ),
    )


def _load_local_repo_config(
    data: dict[str, Any],
    base_dir: Path,
) -> LocalRepoConfig:
    section = _required_mapping(data, "local_repo")
    return LocalRepoConfig(
        upstream_url=_required_str(section, "upstream_url", "local_repo"),
        repo_dir=_required_path(section, "repo_dir", "local_repo", base_dir),
        worktree_dir=_required_path(section, "worktree_dir", "local_repo", base_dir),
    )


def _load_codex_config(data: dict[str, Any]) -> CodexConfig:
    section = _required_mapping(data, "codex")
    return CodexConfig(
        command=_required_str(section, "command", "codex"),
        mode=_required_str(section, "mode", "codex"),
        timeout_seconds=_optional_int(
            section,
            "timeout_seconds",
            DEFAULT_CODEX_TIMEOUT_SECONDS,
            "codex",
        ),
        max_attempts_per_pr=_required_int(section, "max_attempts_per_pr", "codex"),
        result_file=_required_str(section, "result_file", "codex"),
    )


def _load_analysis_config(data: dict[str, Any]) -> AnalysisConfig:
    section = _optional_mapping(data, "analysis")
    return AnalysisConfig(
        default_limit=_optional_int(
            section,
            "default_limit",
            DEFAULT_ANALYSIS_LIMIT,
            "analysis",
        ),
        stale_timeout_seconds=_optional_int(
            section,
            "stale_timeout_seconds",
            DEFAULT_STALE_TIMEOUT_SECONDS,
            "analysis",
        ),
    )


def _load_reports_config(data: dict[str, Any], base_dir: Path) -> ReportsConfig:
    section = _required_mapping(data, "reports")
    return ReportsConfig(
        output_dir=_required_path(section, "output_dir", "reports", base_dir),
    )


def _load_storage_config(data: dict[str, Any], base_dir: Path) -> StorageConfig:
    section = _required_mapping(data, "storage")
    return StorageConfig(
        sqlite_path=_required_path(section, "sqlite_path", "storage", base_dir),
    )


def _load_security_config(data: dict[str, Any], base_dir: Path) -> SecurityConfig:
    section = _optional_mapping(data, "security")
    prefixes = [
        _normalize_path(prefix, base_dir)
        for prefix in _optional_str_list(
            section,
            "forbidden_private_prefixes",
            [],
            "security",
            allow_empty=True,
        )
    ]
    task_dir = None
    if "task_dir" in section:
        task_dir = _required_path(section, "task_dir", "security", base_dir)

    return SecurityConfig(
        forbidden_private_prefixes=prefixes,
        task_dir=task_dir,
    )


def _required_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' is required and must be a mapping.")
    return value


def _optional_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a mapping.")
    return value


def _required_str(section: dict[str, Any], key: str, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Config value '{section_name}.{key}' is required.")
    return value


def _required_int(section: dict[str, Any], key: str, section_name: str) -> int:
    if key not in section:
        raise ValueError(f"Config value '{section_name}.{key}' is required.")
    return _coerce_int(section[key], f"{section_name}.{key}")


def _optional_int(
    section: dict[str, Any],
    key: str,
    default: int,
    section_name: str,
) -> int:
    if key not in section:
        return default
    return _coerce_int(section[key], f"{section_name}.{key}")


def _optional_float(
    section: dict[str, Any],
    key: str,
    default: float,
    section_name: str,
) -> float:
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Config value '{section_name}.{key}' must be a number.")
    return float(value)


def _optional_bool(
    section: dict[str, Any],
    key: str,
    default: bool,
    section_name: str,
) -> bool:
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, bool):
        raise ValueError(f"Config value '{section_name}.{key}' must be a boolean.")
    return value


def _required_str_list(
    section: dict[str, Any],
    key: str,
    section_name: str,
) -> list[str]:
    if key not in section:
        raise ValueError(f"Config value '{section_name}.{key}' is required.")
    return _coerce_str_list(section[key], f"{section_name}.{key}")


def _optional_str_list(
    section: dict[str, Any],
    key: str,
    default: list[str],
    section_name: str,
    allow_empty: bool = False,
) -> list[str]:
    if key not in section:
        return list(default)
    return _coerce_str_list(
        section[key],
        f"{section_name}.{key}",
        allow_empty=allow_empty,
    )


def _required_path(
    section: dict[str, Any],
    key: str,
    section_name: str,
    base_dir: Path,
) -> Path:
    return _normalize_path(_required_str(section, key, section_name), base_dir)


def _normalize_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(strict=False)


def _coerce_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Config value '{name}' must be an integer.")
    return value


def _coerce_str_list(value: Any, name: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Config value '{name}' must be a list.")
    if not value and not allow_empty:
        raise ValueError(f"Config value '{name}' must be a non-empty list.")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Config value '{name}' must contain only non-empty strings.")
    return list(value)


def _reject_embedded_tokens(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, child_value in value.items():
            child_path = f"{path}.{key}"
            normalized = str(key).lower()
            if normalized != "token_env" and (
                normalized in TOKEN_FIELD_NAMES or "token" in normalized
            ):
                raise ValueError(f"Config value '{child_path}' must not embed a token.")
            _reject_embedded_tokens(child_value, child_path)
    elif isinstance(value, list):
        for index, child_value in enumerate(value):
            _reject_embedded_tokens(child_value, f"{path}[{index}]")


def _validate_forbidden_path_overlaps(config: HarnessConfig) -> None:
    if not config.security.forbidden_private_prefixes:
        return

    configured_paths = [
        config.local_repo.repo_dir,
        config.local_repo.worktree_dir,
        config.reports.output_dir,
        config.storage.sqlite_path,
    ]
    if config.security.task_dir is not None:
        configured_paths.append(config.security.task_dir)

    for configured_path in configured_paths:
        for forbidden_prefix in config.security.forbidden_private_prefixes:
            if _paths_overlap(configured_path, forbidden_prefix):
                raise ValueError(
                    "Configured path overlaps forbidden private prefix: "
                    f"{configured_path}"
                )


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_relative_to(left, right) or _is_relative_to(right, left)


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
    except ValueError:
        return False
    return True
