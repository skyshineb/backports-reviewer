from __future__ import annotations

from importlib import resources


PROMPTS_PACKAGE = "backport_harness.prompts"
ANALYZE_TARGET_BRANCH_PROMPT = "analyze_target_branch_pr.md"
ANALYZE_SOURCE_BRANCH_PROMPT = "analyze_source_branch_pr.md"
TRANSPLANT_TEST_PROMPT = "transplant_test.md"
VERIFY_FIX_PROMPT = "verify_fix.md"


def load_prompt_template(name: str) -> str:
    return resources.files(PROMPTS_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def analysis_prompt_for_branch(
    upstream_branch: str,
    *,
    target_ref_label: str | None = None,
) -> str:
    if target_ref_label is not None and upstream_branch == target_ref_label:
        return load_prompt_template(ANALYZE_TARGET_BRANCH_PROMPT)

    return load_prompt_template(ANALYZE_SOURCE_BRANCH_PROMPT)
