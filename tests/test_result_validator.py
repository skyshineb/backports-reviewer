from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backport_harness.result_validator import validate_codex_result_file


def test_valid_master_fix_verified_result(tmp_path: Path) -> None:
    task_dir = _write_result(tmp_path, _valid_result())

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True
    assert outcome.result is not None
    assert outcome.issues == ()


def test_missing_result_file_is_invalid(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "does not exist" in outcome.summary


def test_malformed_result_file_is_invalid(tmp_path: Path) -> None:
    task_dir = _make_task_dir(tmp_path)
    result_path = task_dir / "output" / "codex_result.json"
    result_path.write_text("{not json", encoding="utf-8")

    outcome = validate_codex_result_file(task_dir=task_dir, result_path=result_path)

    assert outcome.valid is False
    assert "schema validation failed" in outcome.summary


def test_schema_invalid_result_file_is_invalid(tmp_path: Path) -> None:
    payload = _valid_result()
    payload["decision"] = "UNKNOWN"
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "schema validation failed" in outcome.summary


def test_missing_referenced_log_is_invalid(tmp_path: Path) -> None:
    task_dir = _write_result(tmp_path, _valid_result())
    (task_dir / "output" / "logs" / "test-before-fix.log").unlink()

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "Referenced log file is missing" in outcome.summary


def test_missing_required_patch_is_invalid(tmp_path: Path) -> None:
    task_dir = _write_result(tmp_path, _valid_result())
    (task_dir / "output" / "patches" / "adapted-fix.patch").unlink()

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "patch file is missing" in outcome.summary


def test_fix_verified_rejects_before_fix_pass(tmp_path: Path) -> None:
    payload = _valid_result()
    payload["test_before_fix"]["exit_code"] = 0
    payload["test_before_fix"]["result"] = "passed"
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "Before-fix test must exit with a non-zero code" in outcome.summary


def test_fix_verified_rejects_after_fix_failure(tmp_path: Path) -> None:
    payload = _valid_result()
    payload["fix_verification"]["exit_code"] = 1
    payload["fix_verification"]["result"] = "failed_after_adapted_fix"
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "Fix verification must exit with code 0" in outcome.summary


def test_valid_master_reproduced_result(tmp_path: Path) -> None:
    payload = _valid_result(decision="MASTER_REPRODUCED_ON_015")
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        payload["evidence"][0],
        payload["evidence"][1],
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True


def test_master_reproduced_requires_expected_failure(tmp_path: Path) -> None:
    payload = _valid_result(decision="MASTER_REPRODUCED_ON_015")
    payload["fix_verification"] = _not_attempted_fix()
    payload["test_before_fix"]["result"] = "failed"
    payload["evidence"][1]["description"] = "Regression test fails."
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "expected bug failure" in outcome.summary


def test_valid_master_not_applicable_result(tmp_path: Path) -> None:
    payload = _valid_result(decision="MASTER_NOT_APPLICABLE")
    payload["applicability"] = {
        "applies_to_oss_015": False,
        "reason": "The affected class is absent in OSS 0.15.",
        "affected_public_paths": [],
        "missing_public_paths": ["hudi-client/src/main/java/example/Foo.java"],
    }
    payload["test_transplant"] = _not_attempted_transplant()
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "non_applicability",
            "description": "The affected class is absent in OSS 0.15.",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True


def test_valid_master_not_applicable_when_fix_already_present(
    tmp_path: Path,
) -> None:
    payload = _valid_result(decision="MASTER_NOT_APPLICABLE")
    payload["applicability"] = {
        "applies_to_oss_015": False,
        "reason": (
            "The affected public OSS 0.15 code exists, but the fix behavior "
            "is already present in HoodieFlinkStreamer append mode."
        ),
        "affected_public_paths": [
            "hudi-flink-datasource/hudi-flink/src/main/java/org/apache/hudi/streamer/HoodieFlinkStreamer.java",
        ],
        "missing_public_paths": [],
    }
    payload["test_transplant"] = _not_attempted_transplant()
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "non_applicability",
            "description": (
                "The target 0.15 worktree already contains the master fix "
                "behavior, so there is no missing public 0.15 hunk to transplant."
            ),
            "path": "hudi-flink-datasource/hudi-flink/src/main/java/org/apache/hudi/streamer/HoodieFlinkStreamer.java",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True


def test_master_not_applicable_requires_strong_reason(tmp_path: Path) -> None:
    payload = _valid_result(decision="MASTER_NOT_APPLICABLE")
    payload["applicability"]["applies_to_oss_015"] = False
    payload["applicability"]["reason"] = "Probably not relevant."
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "non_applicability",
            "description": "Probably not relevant.",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "Non-applicability must cite" in outcome.summary


def test_valid_inconclusive_result(tmp_path: Path) -> None:
    payload = _valid_result(decision="INCONCLUSIVE")
    payload["test_transplant"] = {
        "attempted": True,
        "result": "does_not_compile",
        "notes": "Missing old API equivalent.",
    }
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "uncertainty",
            "description": "The transplanted test does not compile on public OSS 0.15.",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True


def test_inconclusive_requires_uncertainty_evidence(tmp_path: Path) -> None:
    payload = _valid_result(decision="INCONCLUSIVE")
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "classification",
            "description": "Unsure.",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "requires uncertainty evidence" in outcome.summary


def test_valid_failed_infra_result(tmp_path: Path) -> None:
    payload = _valid_result(decision="FAILED_INFRA")
    payload["test_transplant"] = _not_attempted_transplant()
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "infra_failure",
            "description": "Maven dependency resolution failed.",
            "command": "mvn test",
            "exit_code": 1,
            "log_path": "output/logs/infra.log",
        }
    ]
    task_dir = _write_result(tmp_path, payload, logs=("infra.log",))

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is True


def test_failed_infra_requires_identifying_evidence(tmp_path: Path) -> None:
    payload = _valid_result(decision="FAILED_INFRA")
    payload["test_before_fix"] = _not_attempted_test()
    payload["fix_verification"] = _not_attempted_fix()
    payload["evidence"] = [
        {
            "type": "infra_failure",
            "description": "Infrastructure failed.",
        }
    ]
    task_dir = _write_result(tmp_path, payload)

    outcome = validate_codex_result_file(
        task_dir=task_dir,
        result_path=task_dir / "output" / "codex_result.json",
    )

    assert outcome.valid is False
    assert "must identify a command, log path, input path, or exit code" in outcome.summary


def _write_result(
    tmp_path: Path,
    payload: dict[str, Any],
    *,
    logs: tuple[str, ...] = ("test-before-fix.log", "test-after-fix.log"),
    patches: tuple[str, ...] = ("adapted-fix.patch",),
) -> Path:
    task_dir = _make_task_dir(tmp_path)
    for log_name in logs:
        (task_dir / "output" / "logs" / log_name).write_text(
            "log\n",
            encoding="utf-8",
        )
    for patch_name in patches:
        (task_dir / "output" / "patches" / patch_name).write_text(
            "patch\n",
            encoding="utf-8",
        )
    (task_dir / "output" / "codex_result.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return task_dir


def _make_task_dir(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task"
    (task_dir / "output" / "logs").mkdir(parents=True, exist_ok=True)
    (task_dir / "output" / "patches").mkdir(parents=True, exist_ok=True)
    return task_dir


def _valid_result(**overrides: Any) -> dict[str, Any]:
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
                "description": "Regression test fails before the fix with the expected error.",
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
    result.update(copy.deepcopy(overrides))
    return result


def _not_attempted_transplant() -> dict[str, Any]:
    return {
        "attempted": False,
        "result": None,
        "notes": None,
    }


def _not_attempted_test() -> dict[str, Any]:
    return {
        "attempted": False,
        "command": None,
        "exit_code": None,
        "result": None,
        "log_path": None,
    }


def _not_attempted_fix() -> dict[str, Any]:
    return {
        "attempted": False,
        "command": None,
        "exit_code": None,
        "result": None,
        "patch_path": None,
        "log_path": None,
    }
