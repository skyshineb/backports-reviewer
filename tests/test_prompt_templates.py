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


def test_analysis_prompts_list_allowed_decisions() -> None:
    analyze_015 = (PROMPTS_DIR / "analyze_015_pr.md").read_text(encoding="utf-8")
    analyze_master = (PROMPTS_DIR / "analyze_master_pr.md").read_text(
        encoding="utf-8"
    )

    for decision in ANALYZE_015_DECISIONS:
        assert decision in analyze_015

    for decision in ANALYZE_MASTER_DECISIONS:
        assert decision in analyze_master
