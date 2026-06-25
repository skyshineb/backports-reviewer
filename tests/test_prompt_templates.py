import re
from pathlib import Path


PROMPTS_DIR = Path("backport_harness/prompts")
PROMPT_FILES = [
    "analyze_target_branch_pr.md",
    "analyze_source_branch_pr.md",
    "transplant_test.md",
    "verify_fix.md",
]
REQUIRED_JSON_FIELDS = [
    "schema_version",
    "pr_number",
    "upstream_branch",
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
CONFIDENCE_MAPPINGS = [
    "`very_high`: test fails before fix and passes after adapted fix.",
    "`high`: regression test reproduces the bug on the configured public target ref.",
    "`medium`: relevant code/logic exists but no test proof.",
    "`low`: weak relevance signals only.",
    "`unknown`: inconclusive.",
]
FAILED_INFRA_POLICY_SNIPPETS = [
    "Use `FAILED_INFRA` only for one of these infrastructure failures:",
    "- command timeout",
    "- dependency resolution failure",
    "- filesystem error",
    "- unavailable test infrastructure",
    "- unreadable required input files",
    "Logical uncertainty, missing proof, ambiguous applicability, unsupported adaptation, or inability to reason from public code must use `INCONCLUSIVE` or `NEEDS_HUMAN_REVIEW`, not `FAILED_INFRA`.",
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
    "`applies_to_target_ref`: boolean or null when unknown.",
    "`affected_public_paths`: array of repository-relative public paths.",
    "`missing_public_paths`: array of repository-relative public paths.",
    "Interpret `applies_to_target_ref` as applicability to the configured public target ref for this task.",
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
RESULT_VALUE_SNIPPETS = [
    "Allowed result values:",
    "`test_transplant.result`: `not_found`, `not_applicable`, `applied`, `applied_and_compiled`, `does_not_compile`, `failed`, `skipped`, or null.",
    "`test_before_fix.result`: `not_run`, `passed`, `failed`, `failed_with_expected_error`, `failed_with_unrelated_error`, `did_not_compile`, `flaky`, `timeout`, `infra_failed`, or null.",
    "`fix_verification.result`: `not_run`, `passed_after_adapted_fix`, `failed_after_adapted_fix`, `patch_not_applicable`, `did_not_compile`, `flaky`, `timeout`, `infra_failed`, or null.",
    "Do not invent result values.",
    "such as missing `mvn`, use `infra_failed`",
    "`infra_failure` evidence",
]
NOTES_OUTPUT_SNIPPETS = [
    "Write human-readable notes only to `output/notes.md`.",
    "Do not write prose outside `output/codex_result.json` and `output/notes.md`.",
]
TEST_EXECUTION_LIMIT_SNIPPETS = [
    "Run the smallest focused command that can verify the behavior.",
    "Prefer commands in this order: single test method, then test class, then test module.",
    "Avoid full project tests unless no narrower command can verify the behavior.",
    "Record every executed command, exit code, and related log path in `output/codex_result.json`.",
    "Save every test or command log under `output/logs/`.",
]
MODIFICATION_BOUNDARY_SNIPPETS = [
    "Only edit files in the configured public target-ref worktree that are needed for transplant or fix verification.",
    "Do not modify task input files, including `pr.json`, `files_changed.json`, and `pr.diff`.",
    "Write any generated patch under `output/patches/`.",
]
NO_TEST_POLICY_SNIPPETS = [
    "Do not discard a PR only because no regression test exists.",
    "Use `INCONCLUSIVE` when applicability is unsafe to determine from public context.",
]
SOURCE_NO_TEST_POLICY_SNIPPETS = [
    "Do not discard a source-branch PR only because no regression test exists.",
    "Use `SOURCE_POSSIBLY_APPLICABLE` when relevant configured public target-ref code or logic exists but there is no test proof.",
    "Use `INCONCLUSIVE` when applicability is unsafe to determine from public context.",
]
TEST_TRANSPLANT_OUTCOME_SNIPPETS = [
    "No public regression test found: use `SOURCE_POSSIBLY_APPLICABLE` when relevant configured public target-ref code or logic exists; otherwise use `INCONCLUSIVE`.",
    "Test not applicable to the configured public target ref: use `INCONCLUSIVE`.",
    "Transplanted test does not compile: use `INCONCLUSIVE`.",
    "Transplanted test fails with the expected bug before fix: use `SOURCE_REPRODUCED_ON_TARGET`.",
    "Transplanted test fails with an unrelated error: use `INCONCLUSIVE`.",
    "Transplanted test passes before fix: use `SOURCE_POSSIBLY_APPLICABLE` when relevant configured public target-ref code or logic exists; otherwise use `INCONCLUSIVE`.",
    "Transplanted test is flaky: use `INCONCLUSIVE`.",
]
WORKTREE_CONTEXT_SNIPPET = (
    "Configured public target-ref worktree from the rendered task context line "
    "`Configured public target-ref worktree: <path>`"
)
ANALYZE_TARGET_BRANCH_DECISIONS = [
    "TARGET_BRANCH_BUGFIX",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "NEEDS_HUMAN_REVIEW",
    "INCONCLUSIVE",
    "FAILED_INFRA",
]
ANALYZE_SOURCE_BRANCH_DECISIONS = [
    "SOURCE_NOT_APPLICABLE",
    "SOURCE_POSSIBLY_APPLICABLE",
    "SOURCE_REPRODUCED_ON_TARGET",
    "SOURCE_FIX_VERIFIED_ON_TARGET",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "FAILED_INFRA",
]
TRANSPLANT_DECISIONS = [
    "SOURCE_REPRODUCED_ON_TARGET",
    "SOURCE_POSSIBLY_APPLICABLE",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
]
VERIFY_DECISIONS = [
    "SOURCE_FIX_VERIFIED_ON_TARGET",
    "SOURCE_REPRODUCED_ON_TARGET",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
]
DECISIONS_BY_PROMPT = {
    "analyze_target_branch_pr.md": ANALYZE_TARGET_BRANCH_DECISIONS,
    "analyze_source_branch_pr.md": ANALYZE_SOURCE_BRANCH_DECISIONS,
    "transplant_test.md": TRANSPLANT_DECISIONS,
    "verify_fix.md": VERIFY_DECISIONS,
}
TARGET_BRANCH_DECISION_SPECIFIC_REQUIREMENTS = [
    "TARGET_BRANCH_BUGFIX",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
    "classification` evidence",
    "uncertainty` evidence",
    "infra_failure` evidence",
]
SOURCE_BRANCH_DECISION_SPECIFIC_REQUIREMENTS = [
    "SOURCE_FIX_VERIFIED_ON_TARGET",
    "SOURCE_REPRODUCED_ON_TARGET",
    "SOURCE_POSSIBLY_APPLICABLE",
    "SOURCE_NOT_APPLICABLE",
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
    "fix behavior already present in the configured public target ref",
]
TRANSPLANT_DECISION_SPECIFIC_REQUIREMENTS = [
    "SOURCE_REPRODUCED_ON_TARGET",
    "SOURCE_POSSIBLY_APPLICABLE",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
    "code_presence` or `logic_match` evidence",
    "uncertainty` evidence",
    "infra_failure` evidence",
    "`test_failure` evidence",
]
VERIFY_DECISION_SPECIFIC_REQUIREMENTS = [
    "SOURCE_FIX_VERIFIED_ON_TARGET",
    "SOURCE_REPRODUCED_ON_TARGET",
    "INCONCLUSIVE",
    "NEEDS_HUMAN_REVIEW",
    "FAILED_INFRA",
    "uncertainty` evidence",
    "infra_failure` evidence",
    "`test_failure` evidence item",
    "`test_pass` evidence item",
    "`confidence: very_high`",
    "after-fix log path and adapted patch path",
]
SOURCE_INVESTIGATION_SEQUENCE = [
    "1. Read `pr.json` for PR metadata.",
    "2. Inspect `files_changed.json` and `pr.diff`.",
    "3. Classify the PR type.",
    "4. If the PR is non-bugfix, docs-only, CI-only, or release-only, choose the matching discard decision.",
    "5. Inspect production code changes for bugfix behavior.",
    "6. Check whether each affected module, file, class, or method exists in the configured public target-ref worktree.",
    "7. Compare the source-branch logic with the configured public target-ref logic.",
    "8. Decide whether to discard, mark possibly applicable, reproduce with a test, or verify an adapted fix.",
    "9. If a usable public regression test exists, try the smallest focused test transplant.",
    "10. If reproduction succeeds, optionally apply or adapt the public fix in the configured public target-ref worktree, save the adapted patch under `output/patches/`, and rerun the same focused test when possible.",
    "11. Write strict JSON to `output/codex_result.json` and human-readable notes to `output/notes.md`.",
]


def _section(content: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        content,
        re.M | re.S,
    )
    assert match is not None
    return match.group("body")


def _allowed_decisions(content: str) -> list[str]:
    section = _section(content, "Allowed Decisions")
    return re.findall(r"^- `([^`]+)`$", section, re.M)


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
        assert "output/notes.md" in content
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

        for confidence_mapping in CONFIDENCE_MAPPINGS:
            assert confidence_mapping in content

        for evidence_field in EVIDENCE_FIELDS:
            assert f"`{evidence_field}`" in content

        for evidence_type in EVIDENCE_TYPES:
            assert evidence_type in content


def test_prompts_define_exact_result_value_enums() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in RESULT_VALUE_SNIPPETS:
            assert snippet in content


def test_prompts_define_narrow_failed_infra_policy() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        assert "## FAILED_INFRA Policy" in content
        for snippet in FAILED_INFRA_POLICY_SNIPPETS:
            assert snippet in content


def test_prompts_define_notes_output_and_no_extra_prose_policy() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in NOTES_OUTPUT_SNIPPETS:
            assert snippet in content


def test_prompts_define_focused_test_execution_limits() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in TEST_EXECUTION_LIMIT_SNIPPETS:
            assert snippet in content


def test_prompts_define_modification_boundaries() -> None:
    for prompt_file in PROMPT_FILES:
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in MODIFICATION_BOUNDARY_SNIPPETS:
            assert snippet in content


def test_prompts_define_no_test_policy() -> None:
    for prompt_file in ("analyze_target_branch_pr.md", "transplant_test.md", "verify_fix.md"):
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        for snippet in NO_TEST_POLICY_SNIPPETS:
            assert snippet in content

    source_content = (PROMPTS_DIR / "analyze_source_branch_pr.md").read_text(
        encoding="utf-8"
    )
    for snippet in SOURCE_NO_TEST_POLICY_SNIPPETS:
        assert snippet in source_content


def test_transplant_prompts_define_outcome_policy() -> None:
    for prompt_file in ("analyze_source_branch_pr.md", "transplant_test.md"):
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        assert "## Test Transplant Outcome Policy" in content
        for snippet in TEST_TRANSPLANT_OUTCOME_SNIPPETS:
            assert snippet in content


def test_analysis_prompts_rely_on_rendered_worktree_context() -> None:
    for prompt_file in ("analyze_target_branch_pr.md", "analyze_source_branch_pr.md"):
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")

        assert WORKTREE_CONTEXT_SNIPPET in content
        assert "worktree path supplied by the task builder" not in content


def test_prompts_define_decision_specific_evidence_requirements() -> None:
    target_content = (PROMPTS_DIR / "analyze_target_branch_pr.md").read_text(
        encoding="utf-8"
    )
    assert "Decision-specific requirements:" in target_content
    for requirement in TARGET_BRANCH_DECISION_SPECIFIC_REQUIREMENTS:
        assert requirement in target_content

    source_content = (PROMPTS_DIR / "analyze_source_branch_pr.md").read_text(
        encoding="utf-8"
    )
    assert "Decision-specific requirements:" in source_content
    for requirement in SOURCE_BRANCH_DECISION_SPECIFIC_REQUIREMENTS:
        assert requirement in source_content


def test_transplant_and_verify_decision_requirements_are_phase_specific() -> None:
    transplant = (PROMPTS_DIR / "transplant_test.md").read_text(encoding="utf-8")
    verify = (PROMPTS_DIR / "verify_fix.md").read_text(encoding="utf-8")

    assert "Decision-specific requirements:" in transplant
    for requirement in TRANSPLANT_DECISION_SPECIFIC_REQUIREMENTS:
        assert requirement in transplant
    for disallowed_decision in (
        "TARGET_BRANCH_BUGFIX",
        "SOURCE_FIX_VERIFIED_ON_TARGET",
        "SOURCE_NOT_APPLICABLE",
        "DISCARDED_NON_BUGFIX",
        "DISCARDED_DOCS_ONLY",
        "DISCARDED_CI_ONLY",
        "DISCARDED_RELEASE_ONLY",
    ):
        assert disallowed_decision not in _section(
            transplant, "Strict JSON Output"
        )

    assert "Decision-specific requirements:" in verify
    for requirement in VERIFY_DECISION_SPECIFIC_REQUIREMENTS:
        assert requirement in verify
    for disallowed_decision in (
        "TARGET_BRANCH_BUGFIX",
        "SOURCE_POSSIBLY_APPLICABLE",
        "SOURCE_NOT_APPLICABLE",
        "DISCARDED_NON_BUGFIX",
        "DISCARDED_DOCS_ONLY",
        "DISCARDED_CI_ONLY",
        "DISCARDED_RELEASE_ONLY",
    ):
        assert disallowed_decision not in _section(verify, "Strict JSON Output")


def test_prompts_list_exact_allowed_decisions() -> None:
    for prompt_file, expected_decisions in DECISIONS_BY_PROMPT.items():
        content = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
        assert _allowed_decisions(content) == expected_decisions


def test_source_prompt_defines_required_investigation_sequence_in_order() -> None:
    content = (PROMPTS_DIR / "analyze_source_branch_pr.md").read_text(encoding="utf-8")
    position = -1

    for step in SOURCE_INVESTIGATION_SEQUENCE:
        next_position = content.find(step, position + 1)
        assert next_position > position
        position = next_position
