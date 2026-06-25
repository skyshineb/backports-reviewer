from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from backport_harness.codex_result import (
    Confidence,
    Decision,
    EvidenceType,
    FixVerificationResult,
    TestResult as CodexTestResult,
    TransplantResult,
    load_codex_result,
    parse_codex_result_json,
)


def valid_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "pr_number": 12345,
        "target_branch": "master",
        "decision": "MASTER_FIX_VERIFIED_ON_015",
        "confidence": "very_high",
        "bugfix_classification": "correctness_bugfix",
        "summary": "Fixes null handling in compaction scheduling.",
        "human_action": "Review adapted patch and backport if appropriate.",
        "applicability": {
            "applies_to_oss_015": True,
            "reason": "The affected class and method exist in OSS 0.15.",
            "affected_public_paths": [
                "hudi-client/src/main/java/example/Foo.java",
            ],
            "missing_public_paths": [],
        },
        "touched_components": ["hudi-client", "compaction"],
        "production_files_relevant_to_015": [
            "hudi-client/src/main/java/example/Foo.java",
        ],
        "test_files_used": [
            "hudi-client/src/test/java/example/TestFoo.java",
        ],
        "test_transplant": {
            "attempted": True,
            "result": "applied_and_compiled",
            "notes": "Adapted imports to 0.15 APIs.",
        },
        "test_before_fix": {
            "attempted": True,
            "command": "mvn -pl hudi-client -Dtest=TestFoo#testNullCase test",
            "exit_code": 1,
            "result": "failed_with_expected_error",
            "log_path": "output/logs/test-before-fix.log",
        },
        "fix_verification": {
            "attempted": True,
            "command": "mvn -pl hudi-client -Dtest=TestFoo#testNullCase test",
            "exit_code": 0,
            "result": "passed_after_adapted_fix",
            "patch_path": "output/patches/adapted-fix.patch",
            "log_path": "output/logs/test-after-fix.log",
        },
        "evidence": [
            {
                "type": "code_presence",
                "description": "Class Foo exists in OSS 0.15.",
                "path": "hudi-client/src/main/java/example/Foo.java",
            },
            {
                "type": "test_failure",
                "description": "Regression test fails before the fix.",
                "log_path": "output/logs/test-before-fix.log",
                "command": "mvn test",
                "exit_code": 1,
            },
            {
                "type": "test_pass",
                "description": "The same test passes after the adapted fix.",
                "log_path": "output/logs/test-after-fix.log",
                "patch_path": "output/patches/adapted-fix.patch",
                "exit_code": 0,
            },
        ],
    }
    result.update(overrides)
    return result


def parse_result(payload: dict[str, Any]):
    return parse_codex_result_json(json.dumps(payload))


def test_parse_valid_master_result() -> None:
    result = parse_result(valid_result())

    assert result.decision is Decision.MASTER_FIX_VERIFIED_ON_015
    assert result.confidence is Confidence.VERY_HIGH
    assert result.evidence[0].type is EvidenceType.CODE_PRESENCE


def test_parse_valid_015_result() -> None:
    payload = valid_result(
        target_branch="0.15",
        decision="DIRECT_015_BUGFIX",
        confidence="medium",
        fix_verification={
            "attempted": False,
            "command": None,
            "exit_code": None,
            "result": None,
            "patch_path": None,
            "log_path": None,
        },
    )

    result = parse_result(payload)

    assert result.target_branch == "0.15"
    assert result.decision is Decision.DIRECT_015_BUGFIX
    assert result.fix_verification.result is None


def test_parse_valid_configured_upstream_branch_result() -> None:
    result = parse_result(valid_result(target_branch="main"))

    assert result.target_branch == "main"


def test_load_codex_result_from_path(tmp_path: Path) -> None:
    result_path = tmp_path / "codex_result.json"
    result_path.write_text(json.dumps(valid_result()), encoding="utf-8")

    result = load_codex_result(result_path)

    assert result.pr_number == 12345


def test_malformed_json_fails_validation() -> None:
    with pytest.raises(ValueError, match="Invalid Codex result JSON"):
        parse_codex_result_json("{not json")


def test_missing_required_field_fails_validation() -> None:
    payload = valid_result()
    del payload["human_action"]

    with pytest.raises(ValidationError, match="human_action"):
        parse_result(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("decision", "UNKNOWN_DECISION"),
        ("confidence", "certain"),
        ("schema_version", 2),
    ],
)
def test_unknown_or_unsupported_top_level_values_fail_validation(
    field_name: str,
    value: Any,
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        parse_result(valid_result(**{field_name: value}))


def test_unknown_evidence_type_fails_validation() -> None:
    payload = valid_result()
    payload["evidence"][0]["type"] = "screenshot"

    with pytest.raises(ValidationError, match="evidence"):
        parse_result(payload)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("summary", "", "summary"),
        ("human_action", "", "human_action"),
        (
            "applicability",
            {
                "applies_to_oss_015": True,
                "reason": "",
                "affected_public_paths": [],
                "missing_public_paths": [],
            },
            "reason",
        ),
        (
            "evidence",
            [
                {
                    "type": "classification",
                    "description": "",
                },
            ],
            "description",
        ),
    ],
)
def test_empty_required_strings_fail_validation(
    field_name: str,
    value: Any,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_result(valid_result(**{field_name: value}))


def test_empty_evidence_fails_validation() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        parse_result(valid_result(evidence=[]))


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/private.log",
        "../private.log",
        "output/../private.log",
    ],
)
def test_evidence_paths_must_be_relative_without_parent_segments(
    path: str,
) -> None:
    payload = valid_result()
    payload["evidence"][0]["path"] = path

    with pytest.raises(ValidationError, match="path"):
        parse_result(payload)


def test_log_path_must_be_under_output_logs() -> None:
    payload = valid_result()
    payload["test_before_fix"]["log_path"] = "logs/test.log"

    with pytest.raises(ValidationError, match="output/logs/"):
        parse_result(payload)


def test_patch_path_must_be_under_output_patches() -> None:
    payload = valid_result()
    payload["fix_verification"]["patch_path"] = "patches/fix.patch"

    with pytest.raises(ValidationError, match="output/patches/"):
        parse_result(payload)


def test_optional_nulls_are_accepted_for_not_attempted_steps() -> None:
    payload = valid_result(
        test_transplant={
            "attempted": False,
            "result": None,
            "notes": None,
        },
        test_before_fix={
            "attempted": False,
            "command": None,
            "exit_code": None,
            "result": None,
            "log_path": None,
        },
        fix_verification={
            "attempted": False,
            "command": None,
            "exit_code": None,
            "result": None,
            "patch_path": None,
            "log_path": None,
        },
    )

    result = parse_result(payload)

    assert result.test_transplant.result is None
    assert result.test_before_fix.log_path is None
    assert result.fix_verification.patch_path is None


@pytest.mark.parametrize(
    "transplant_result",
    [
        "not_found",
        "not_applicable",
        "applied",
        "applied_and_compiled",
        "does_not_compile",
        "failed",
        "skipped",
    ],
)
def test_supported_test_transplant_results_parse(transplant_result: str) -> None:
    payload = valid_result()
    payload["test_transplant"]["result"] = transplant_result

    result = parse_result(payload)

    assert result.test_transplant.result is TransplantResult(transplant_result)


@pytest.mark.parametrize(
    "test_result",
    [
        "passed",
        "failed",
        "failed_with_expected_error",
        "failed_with_unrelated_error",
        "did_not_compile",
        "flaky",
        "timeout",
        "infra_failed",
    ],
)
def test_supported_before_fix_test_results_parse(test_result: str) -> None:
    payload = valid_result()
    payload["test_before_fix"]["result"] = test_result

    result = parse_result(payload)

    assert result.test_before_fix.result is CodexTestResult(test_result)


@pytest.mark.parametrize(
    "fix_verification_result",
    [
        "passed_after_adapted_fix",
        "failed_after_adapted_fix",
        "patch_not_applicable",
        "did_not_compile",
        "flaky",
        "timeout",
        "infra_failed",
    ],
)
def test_supported_fix_verification_results_parse(
    fix_verification_result: str,
) -> None:
    payload = valid_result()
    payload["fix_verification"]["result"] = fix_verification_result

    result = parse_result(payload)

    assert result.fix_verification.result is FixVerificationResult(
        fix_verification_result
    )


@pytest.mark.parametrize(
    ("section_name", "value"),
    [
        ("test_before_fix", "failed_to_start_maven_unavailable"),
        ("fix_verification", "failed_to_start_maven_unavailable"),
    ],
)
def test_ad_hoc_infra_result_values_fail_validation(
    section_name: str,
    value: str,
) -> None:
    payload = valid_result()
    payload[section_name]["result"] = value

    with pytest.raises(ValidationError, match=section_name):
        parse_result(payload)


def test_unknown_extra_fields_fail_validation() -> None:
    payload = valid_result(unexpected="value")

    with pytest.raises(ValidationError, match="unexpected"):
        parse_result(payload)
