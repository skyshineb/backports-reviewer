from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Decision(StrEnum):
    DIRECT_015_BUGFIX = "DIRECT_015_BUGFIX"
    MASTER_NOT_APPLICABLE = "MASTER_NOT_APPLICABLE"
    MASTER_POSSIBLY_APPLICABLE = "MASTER_POSSIBLY_APPLICABLE"
    MASTER_REPRODUCED_ON_015 = "MASTER_REPRODUCED_ON_015"
    MASTER_FIX_VERIFIED_ON_015 = "MASTER_FIX_VERIFIED_ON_015"
    INCONCLUSIVE = "INCONCLUSIVE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    DISCARDED_NON_BUGFIX = "DISCARDED_NON_BUGFIX"
    DISCARDED_DOCS_ONLY = "DISCARDED_DOCS_ONLY"
    DISCARDED_CI_ONLY = "DISCARDED_CI_ONLY"
    DISCARDED_RELEASE_ONLY = "DISCARDED_RELEASE_ONLY"
    FAILED_INFRA = "FAILED_INFRA"


class Confidence(StrEnum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class EvidenceType(StrEnum):
    CODE_PRESENCE = "code_presence"
    LOGIC_MATCH = "logic_match"
    TEST_FAILURE = "test_failure"
    TEST_PASS = "test_pass"
    NON_APPLICABILITY = "non_applicability"
    CLASSIFICATION = "classification"
    INFRA_FAILURE = "infra_failure"
    UNCERTAINTY = "uncertainty"


class TransplantResult(StrEnum):
    NOT_FOUND = "not_found"
    NOT_APPLICABLE = "not_applicable"
    APPLIED = "applied"
    APPLIED_AND_COMPILED = "applied_and_compiled"
    DOES_NOT_COMPILE = "does_not_compile"
    FAILED = "failed"
    SKIPPED = "skipped"


class TestResult(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    FAILED_WITH_EXPECTED_ERROR = "failed_with_expected_error"
    FAILED_WITH_UNRELATED_ERROR = "failed_with_unrelated_error"
    DID_NOT_COMPILE = "did_not_compile"
    FLAKY = "flaky"
    TIMEOUT = "timeout"
    INFRA_FAILED = "infra_failed"


class FixVerificationResult(StrEnum):
    NOT_RUN = "not_run"
    PASSED_AFTER_ADAPTED_FIX = "passed_after_adapted_fix"
    FAILED_AFTER_ADAPTED_FIX = "failed_after_adapted_fix"
    PATCH_NOT_APPLICABLE = "patch_not_applicable"
    DID_NOT_COMPILE = "did_not_compile"
    FLAKY = "flaky"
    TIMEOUT = "timeout"
    INFRA_FAILED = "infra_failed"


class CodexResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Applicability(CodexResultModel):
    applies_to_oss_015: bool | None
    reason: str = Field(min_length=1)
    affected_public_paths: list[str] = Field(default_factory=list)
    missing_public_paths: list[str] = Field(default_factory=list)

    @field_validator("affected_public_paths", "missing_public_paths", mode="after")
    @classmethod
    def validate_repo_paths(cls, paths: list[str]) -> list[str]:
        return [_validate_relative_path(path, "repository path") for path in paths]


class TestTransplant(CodexResultModel):
    attempted: bool
    result: TransplantResult | None
    notes: str | None = None


class TestRunClaim(CodexResultModel):
    attempted: bool
    command: str | None
    exit_code: int | None
    result: TestResult | None
    log_path: str | None

    @field_validator("log_path", mode="after")
    @classmethod
    def validate_log_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_prefixed_path(path, "output/logs/", "log_path")


class FixVerification(CodexResultModel):
    attempted: bool
    command: str | None
    exit_code: int | None
    result: FixVerificationResult | None
    patch_path: str | None
    log_path: str | None

    @field_validator("patch_path", mode="after")
    @classmethod
    def validate_patch_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_prefixed_path(path, "output/patches/", "patch_path")

    @field_validator("log_path", mode="after")
    @classmethod
    def validate_log_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_prefixed_path(path, "output/logs/", "log_path")


class Evidence(CodexResultModel):
    type: EvidenceType
    description: str = Field(min_length=1)
    path: str | None = None
    log_path: str | None = None
    patch_path: str | None = None
    command: str | None = None
    exit_code: int | None = None

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_relative_path(path, "path")

    @field_validator("log_path", mode="after")
    @classmethod
    def validate_log_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_prefixed_path(path, "output/logs/", "log_path")

    @field_validator("patch_path", mode="after")
    @classmethod
    def validate_patch_path(cls, path: str | None) -> str | None:
        if path is None:
            return None
        return _validate_prefixed_path(path, "output/patches/", "patch_path")


class CodexResult(CodexResultModel):
    schema_version: Literal[1]
    pr_number: int
    target_branch: str = Field(min_length=1)
    decision: Decision
    confidence: Confidence
    summary: str = Field(min_length=1)
    human_action: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    applicability: Applicability
    test_transplant: TestTransplant
    test_before_fix: TestRunClaim
    fix_verification: FixVerification
    bugfix_classification: str | None = None
    touched_components: list[str] = Field(default_factory=list)
    production_files_relevant_to_015: list[str] = Field(default_factory=list)
    test_files_used: list[str] = Field(default_factory=list)

    @field_validator(
        "production_files_relevant_to_015",
        "test_files_used",
        mode="after",
    )
    @classmethod
    def validate_repo_paths(cls, paths: list[str]) -> list[str]:
        return [_validate_relative_path(path, "repository path") for path in paths]


def parse_codex_result_json(raw: str | bytes) -> CodexResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid Codex result JSON: {error}") from error
    return CodexResult.model_validate(payload)


def load_codex_result(path: Path) -> CodexResult:
    return parse_codex_result_json(path.read_text(encoding="utf-8"))


def _validate_prefixed_path(path: str, prefix: str, field_name: str) -> str:
    validated = _validate_relative_path(path, field_name)
    if not validated.startswith(prefix):
        raise ValueError(f"{field_name} must be under {prefix}")
    if validated == prefix.rstrip("/"):
        raise ValueError(f"{field_name} must include a file name")
    return validated


def _validate_relative_path(path: str, field_name: str) -> str:
    if not path:
        raise ValueError(f"{field_name} must not be empty")

    posix_path = PurePosixPath(path)
    if posix_path.is_absolute():
        raise ValueError(f"{field_name} must be relative")
    if any(part == ".." for part in posix_path.parts):
        raise ValueError(f"{field_name} must not contain '..'")
    return path


__all__ = [
    "Applicability",
    "CodexResult",
    "Confidence",
    "Decision",
    "Evidence",
    "EvidenceType",
    "FixVerification",
    "FixVerificationResult",
    "TestResult",
    "TestRunClaim",
    "TestTransplant",
    "TransplantResult",
    "ValidationError",
    "load_codex_result",
    "parse_codex_result_json",
]
