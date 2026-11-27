from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CodexBackendName(str, Enum):
    API = "api"
    CLI = "cli"


class ProfileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    upstream: str = "lance-format/lance"
    upstream_branch: str = "main"
    base_ref: str = Field(min_length=1, max_length=240)
    fork_path: Path
    target_branch: str = Field(min_length=1, max_length=240)
    interval_minutes: int = Field(default=30, ge=1, le=1440)
    match_words: str = Field(default="fix bug bugfix", min_length=1, max_length=200)
    analysis_limit: int = Field(default=5, ge=0, le=100)

    @field_validator("upstream")
    @classmethod
    def public_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("Use a public GitHub repository in owner/repo format.")
        if value.split("/")[1] in {".", ".."}:
            raise ValueError("Enter a repository name.")
        return value.lower()

    @field_validator("upstream_branch", "target_branch", "base_ref")
    @classmethod
    def ref_text(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,239}", value):
            raise ValueError("Use a branch name, release tag, or Git SHA.")
        return value

    @field_validator("match_words")
    @classmethod
    def scan_words(cls, value: str) -> str:
        words = value.lower().split()
        if not words or any(not re.fullmatch(r"[a-z0-9_-]+", word) for word in words):
            raise ValueError("Enter a space-separated list of title words.")
        return " ".join(dict.fromkeys(words))


@dataclass(frozen=True)
class SourceCommit:
    sha: str
    parents: tuple[str, ...]
    committed_at: str
    subject: str
    description: str


@dataclass(frozen=True)
class ScanBatch:
    head: str
    base: str
    commits: list[SourceCommit]


@dataclass(frozen=True)
class PreparedPatch:
    expected_sha: str
    sha: str
    diff: str
