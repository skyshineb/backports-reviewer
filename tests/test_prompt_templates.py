from pathlib import Path


PROMPTS_DIR = Path("prompts")
PROMPT_FILES = [
    "analyze_015_pr.md",
    "analyze_master_pr.md",
    "transplant_test.md",
    "verify_fix.md",
]
REQUIRED_JSON_FIELDS = [
    "schema_version",
    "pr_number",
    "target_branch",
    "decision",
    "confidence",
    "summary",
    "human_action",
    "evidence",
    "applicability",
    "test_transplant",
    "test_before_fix",
    "fix_verification",
]
CONFIDENCE_VALUES = [
    "very_high",
    "high",
    "medium",
    "low",
    "unknown",
]
EVIDENCE_FIELDS = [
    "type",
    "description",
    "path",
    "log_path",
    "patch_path",
    "command",
    "exit_code",
]
EVIDENCE_TYPES = [
    "code_presence",
    "logic_match",
    "test_failure",
    "test_pass",
    "non_applicability",
    "classification",
    "infra_failure",
    "uncertainty",
]
STRUCTURED_CONTRACT_SNIPPETS = [
    "`confidence` must be one of:",
    "`applicability` must be an object with:",
    "`applies_to_oss_015`: boolean or null when unknown.",
    "`affected_public_paths`: array of repository-relative public paths.",
    "`missing_public_paths`: array of repository-relative public paths.",
    "`test_transplant` must be an object with:",
    "`test_before_fix` must be an object with:",
    "`fix_verification` must be an object with:",
    "`evidence` must be an array of objects.",
    "All paths in JSON must be relative.",
    "Do not use absolute paths or `..` path segments.",
    "Repository paths must be repository-relative.",
    "Log paths must be under `output/logs/`.",
    "Patch paths must be under `output/patches/`.",
    "Use null only for fields that are explicitly unavailable",
]
ANALYZE_015_DECISIONS = [
    "DIRECT_015_BUGFIX",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "NEEDS_HUMAN_REVIEW",
    "INCONCLUSIVE",
    "FAILED_INFRA",
]
ANALYZE_MASTER_DECISIONS = [
    "MASTER_NOT_APPLICABLE",
    "MASTER_POSSIBLY_APPLICABLE",
    "MASTER_REPRODUCED_ON_015",
    "MASTER_FIX_VERIFIED_ON_015",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "FAILED_INFRA",
]
DECISION_SPECIFIC_REQUIREMENTS = [
    "DIRECT_015_BUGFIX",
    "MASTER_FIX_VERIFIED_ON_015",
    "MASTER_REPRODUCED_ON_015",
    "MASTER_POSSIBLY_APPLICABLE",
    "MASTER_NOT_APPLICABLE",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
    "classification` evidence",
    "non_applicability` evidence",
    "uncertainty` evidence",
    "infra_failure` evidence",
    "`test_failure` evidence item",
    "`test_pass` evidence item",
]
MASTER_INVESTIGATION_SEQUENCE = [
    "1. Read `pr.json` for PR metadata.",
    "2. Inspect `files_changed.json` and `pr.diff`.",
    "3. Classify the PR type.",
    "4. If the PR is non-bugfix, docs-only, CI-only, or release-only, choose the matching discard decision.",
    "5. Inspect production code changes for bugfix behavior.",
    "6. Check whether each affected module, file, class, or method exists in the public OSS 0.15 worktree.",
    "7. Compare the master logic with the public OSS 0.15 logic.",
    "8. Decide whether to discard, mark possibly applicable, reproduce with a test, or verify an adapted fix.",
    "9. If a usable public regression test exists, try the smallest focused test transplant.",
    "10. If reproduction succeeds, optionally apply or adapt the public fix and verify with the focused test.",
    "11. Write strict JSON to `output/codex_result.json`.",
]


def test_prompt_files_exist() -> None:
    for prompt_file in PROMPT_FILES:
        assert (PROMPTS_DIR / prompt_file).is_file()


def test_prompts_include_security_boundary_json_contract_and_uncertain_policy() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
        assert "Security Boundary" in content
        assert "private fork code" in content
        assert "private patches" in content
        assert "private repository history" in content
        assert "private test data" in content
        assert "strict JSON" in content
        assert "output/codex_result.json" in content
        assert "INCONCLUSIVE" in content or "NEEDS_HUMAN_REVIEW" in content
        for required_field in REQUIRED_JSON_FIELDS:
            assert required_field in content


def test_prompts_define_structured_json_contract() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in STRUCTURED_CONTRACT_SNIPPETS:
            assert snippet in content

        for confidence_value in CONFIDENCE_VALUES:
            assert confidence_value in content

        for evidence_field in EVIDENCE_FIELDS:
            assert f"`{evidence_field}`" in content

        for evidence_type in EVIDENCE_TYPES:
            assert evidence_type in content


def test_prompts_define_decision_specific_evidence_requirements() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        assert "Decision-specific requirements:" in content
        for requirement in DECISION_SPECIFIC_REQUIREMENTS:
            assert requirement in content


def test_analysis_prompts_list_allowed_decisions() -> None:
    analyze_015 = (PROMPTS_DIR / "analyze_015_pr.md").read_text(encoding="utf-8")
    analyze_master = (PROMPTS_DIR / "analyze_master_pr.md").read_text(
        encoding="utf-8"
    )

    for decision in ANALYZE_015_DECISIONS:
        assert decision in analyze_015

    for decision in ANALYZE_MASTER_DECISIONS:
        assert decision in analyze_master


def test_master_prompt_defines_required_investigation_sequence_in_order() -> None:
    content = (PROMPTS_DIR / "analyze_master_pr.md").read_text(encoding="utf-8")
    position = -1

    for step in MASTER_INVESTIGATION_SEQUENCE:
        next_position = content.find(step, position + 1)
        assert next_position > position
        position = next_position
