from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from backport_harness.codex_result import (
    CodexResult,
    Decision,
    Evidence,
    EvidenceType,
    FixVerificationResult,
    TestResult,
    TransplantResult,
    load_codex_result,
)


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ValidationOutcome:
    valid: bool
    result: CodexResult | None = None
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def summary(self) -> str:
        if self.valid:
            return "Codex result validated."
        return "; ".join(f"{issue.field}: {issue.message}" for issue in self.issues)


def validate_codex_result_file(*, task_dir: Path, result_path: Path) -> ValidationOutcome:
    issues: list[ValidationIssue] = []
    if not result_path.exists():
        return _invalid("result_path", f"Codex result file does not exist: {result_path}")

    try:
        result = load_codex_result(result_path)
    except (OSError, ValueError, ValidationError) as error:
        return _invalid("result_path", f"Codex result schema validation failed: {error}")

    issues.extend(_validate_referenced_logs(task_dir, result))
    issues.extend(_validate_referenced_patches(task_dir, result))
    issues.extend(_validate_decision_specific_claims(task_dir, result))

    if issues:
        return ValidationOutcome(valid=False, result=result, issues=tuple(issues))
    return ValidationOutcome(valid=True, result=result)


def _validate_referenced_logs(task_dir: Path, result: CodexResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    log_paths = [
        ("test_before_fix.log_path", result.test_before_fix.log_path),
        ("fix_verification.log_path", result.fix_verification.log_path),
    ]
    log_paths.extend(
        (f"evidence[{index}].log_path", evidence.log_path)
        for index, evidence in enumerate(result.evidence)
    )

    for field, log_path in log_paths:
        if log_path is not None and not _bundle_path_exists(task_dir, log_path):
            issues.append(ValidationIssue(field, f"Referenced log file is missing: {log_path}"))
    return issues


def _validate_referenced_patches(task_dir: Path, result: CodexResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    patch_paths = [
        ("fix_verification.patch_path", result.fix_verification.patch_path),
    ]
    patch_paths.extend(
        (f"evidence[{index}].patch_path", evidence.patch_path)
        for index, evidence in enumerate(result.evidence)
    )

    for field, patch_path in patch_paths:
        if patch_path is not None and not _bundle_path_exists(task_dir, patch_path):
            issues.append(
                ValidationIssue(field, f"Referenced patch file is missing: {patch_path}")
            )
    return issues


def _validate_decision_specific_claims(
    task_dir: Path,
    result: CodexResult,
) -> list[ValidationIssue]:
    if result.decision is Decision.MASTER_FIX_VERIFIED_ON_015:
        return _validate_master_fix_verified(task_dir, result)
    if result.decision is Decision.MASTER_REPRODUCED_ON_015:
        return _validate_master_reproduced(result)
    if result.decision is Decision.MASTER_POSSIBLY_APPLICABLE:
        return _validate_master_possibly_applicable(result)
    if result.decision is Decision.MASTER_NOT_APPLICABLE:
        return _validate_master_not_applicable(result)
    if result.decision in {Decision.INCONCLUSIVE, Decision.NEEDS_HUMAN_REVIEW}:
        return _validate_uncertain(result)
    if result.decision is Decision.FAILED_INFRA:
        return _validate_failed_infra(result)
    return []


def _validate_master_fix_verified(
    task_dir: Path,
    result: CodexResult,
) -> list[ValidationIssue]:
    issues = _validate_master_reproduced(result)

    if not result.fix_verification.attempted:
        issues.append(
            ValidationIssue(
                "fix_verification.attempted",
                "Fix verification must be attempted.",
            )
        )
    if result.fix_verification.exit_code != 0:
        issues.append(
            ValidationIssue(
                "fix_verification.exit_code",
                "Fix verification must exit with code 0.",
            )
        )
    if result.fix_verification.result is not FixVerificationResult.PASSED_AFTER_ADAPTED_FIX:
        issues.append(
            ValidationIssue(
                "fix_verification.result",
                "Fix verification must claim passed_after_adapted_fix.",
            )
        )
    if result.fix_verification.patch_path is None:
        issues.append(
            ValidationIssue(
                "fix_verification.patch_path",
                "Fix verification must provide a patch path.",
            )
        )
    elif not _bundle_path_exists(task_dir, result.fix_verification.patch_path):
        issues.append(
            ValidationIssue(
                "fix_verification.patch_path",
                f"Required patch file is missing: {result.fix_verification.patch_path}",
            )
        )

    if not _has_evidence(result, EvidenceType.TEST_PASS):
        issues.append(
            ValidationIssue("evidence", "MASTER_FIX_VERIFIED_ON_015 requires test_pass evidence.")
        )
    return issues


def _validate_master_reproduced(result: CodexResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not result.test_transplant.attempted:
        issues.append(
            ValidationIssue(
                "test_transplant.attempted",
                "Regression test transplant must be attempted.",
            )
        )
    if result.test_transplant.result not in {
        TransplantResult.APPLIED,
        TransplantResult.APPLIED_AND_COMPILED,
    }:
        issues.append(
            ValidationIssue(
                "test_transplant.result",
                "Regression test transplant must be applied before claiming reproduction.",
            )
        )
    if not result.test_before_fix.attempted:
        issues.append(
            ValidationIssue(
                "test_before_fix.attempted",
                "Before-fix test must be attempted.",
            )
        )
    if result.test_before_fix.exit_code is None or result.test_before_fix.exit_code == 0:
        issues.append(
            ValidationIssue(
                "test_before_fix.exit_code",
                "Before-fix test must exit with a non-zero code.",
            )
        )
    if result.test_before_fix.log_path is None:
        issues.append(
            ValidationIssue(
                "test_before_fix.log_path",
                "Before-fix test must provide a log path.",
            )
        )
    if not _has_evidence(result, EvidenceType.TEST_FAILURE):
        issues.append(
            ValidationIssue("evidence", "MASTER_REPRODUCED_ON_015 requires test_failure evidence.")
        )
    if (
        result.test_before_fix.result is not TestResult.FAILED_WITH_EXPECTED_ERROR
        and not _has_expected_failure_description(result.evidence)
    ):
        issues.append(
            ValidationIssue(
                "test_before_fix.result",
                "Before-fix failure must identify the expected bug failure.",
            )
        )
    return issues


def _validate_master_possibly_applicable(result: CodexResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if result.applicability.applies_to_oss_015 is False:
        issues.append(
            ValidationIssue(
                "applicability.applies_to_oss_015",
                "MASTER_POSSIBLY_APPLICABLE requires applies_to_oss_015=true or unknown.",
            )
        )
    if not (
        _has_evidence(result, EvidenceType.CODE_PRESENCE)
        or _has_evidence(result, EvidenceType.LOGIC_MATCH)
    ):
        issues.append(
            ValidationIssue(
                "evidence",
                "MASTER_POSSIBLY_APPLICABLE requires code_presence or logic_match evidence.",
            )
        )
    if result.test_before_fix.result in {
        TestResult.FAILED,
        TestResult.FAILED_WITH_UNRELATED_ERROR,
        TestResult.DID_NOT_COMPILE,
        TestResult.FLAKY,
        TestResult.TIMEOUT,
    }:
        issues.append(
            ValidationIssue(
                "test_before_fix.result",
                "Failed, non-compiling, flaky, or timed-out transplant tests must use INCONCLUSIVE.",
            )
        )
    return issues


def _validate_master_not_applicable(result: CodexResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if result.applicability.applies_to_oss_015 is not False:
        issues.append(
            ValidationIssue(
                "applicability.applies_to_oss_015",
                "MASTER_NOT_APPLICABLE requires applies_to_oss_015=false.",
            )
        )
    non_applicability = [
        evidence
        for evidence in result.evidence
        if evidence.type is EvidenceType.NON_APPLICABILITY
    ]
    if not non_applicability:
        issues.append(
            ValidationIssue(
                "evidence",
                "MASTER_NOT_APPLICABLE requires non_applicability evidence.",
            )
        )

    basis_text = " ".join(
        [result.applicability.reason]
        + [evidence.description for evidence in non_applicability]
    )
    if not _mentions_strong_non_applicability_basis(basis_text):
        issues.append(
            ValidationIssue(
                "applicability.reason",
                "Non-applicability must cite absent file, class, module, feature, bug introduced after 0.15, or fix behavior already present in OSS 0.15.",
            )
        )
    return issues


def _validate_uncertain(result: CodexResult) -> list[ValidationIssue]:
    if _has_evidence(result, EvidenceType.UNCERTAINTY):
        return []
    return [
        ValidationIssue(
            "evidence",
            f"{result.decision.value} requires uncertainty evidence.",
        ),
    ]


def _validate_failed_infra(result: CodexResult) -> list[ValidationIssue]:
    infra_evidence = [
        evidence for evidence in result.evidence if evidence.type is EvidenceType.INFRA_FAILURE
    ]
    if not infra_evidence:
        return [
            ValidationIssue("evidence", "FAILED_INFRA requires infra_failure evidence.")
        ]
    if not any(_identifies_infra_failure(evidence) for evidence in infra_evidence):
        return [
            ValidationIssue(
                "evidence",
                "FAILED_INFRA evidence must identify a command, log path, input path, or exit code.",
            )
        ]
    return []


def _has_evidence(result: CodexResult, evidence_type: EvidenceType) -> bool:
    return any(evidence.type is evidence_type for evidence in result.evidence)


def _has_expected_failure_description(evidence_items: list[Evidence]) -> bool:
    return any(
        evidence.type is EvidenceType.TEST_FAILURE
        and "expected" in evidence.description.lower()
        for evidence in evidence_items
    )


def _mentions_strong_non_applicability_basis(text: str) -> bool:
    normalized = text.lower()
    return (
        ("absent" in normalized and "file" in normalized)
        or ("missing" in normalized and "file" in normalized)
        or ("absent" in normalized and "class" in normalized)
        or ("missing" in normalized and "class" in normalized)
        or ("absent" in normalized and "module" in normalized)
        or ("missing" in normalized and "module" in normalized)
        or ("absent" in normalized and "feature" in normalized)
        or ("missing" in normalized and "feature" in normalized)
        or "introduced after 0.15" in normalized
        or "introduced after `0.15`" in normalized
        or ("already present" in normalized and "0.15" in normalized)
        or ("already contains" in normalized and "0.15" in normalized)
        or (
            "fix behavior" in normalized
            and "already" in normalized
            and "0.15" in normalized
        )
    )


def _identifies_infra_failure(evidence: Evidence) -> bool:
    return any(
        value is not None
        for value in (
            evidence.command,
            evidence.log_path,
            evidence.path,
            evidence.exit_code,
        )
    )


def _bundle_path_exists(task_dir: Path, relative_path: str) -> bool:
    candidate = (task_dir / relative_path).resolve()
    task_root = task_dir.resolve()
    return candidate.is_relative_to(task_root) and candidate.is_file()


def _invalid(field: str, message: str) -> ValidationOutcome:
    return ValidationOutcome(
        valid=False,
        issues=(ValidationIssue(field=field, message=message),),
    )


__all__ = [
    "ValidationIssue",
    "ValidationOutcome",
    "validate_codex_result_file",
]
