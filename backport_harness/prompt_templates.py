from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
ANALYZE_015_PROMPT = "analyze_015_pr.md"
ANALYZE_MASTER_PROMPT = "analyze_master_pr.md"
TRANSPLANT_TEST_PROMPT = "transplant_test.md"
VERIFY_FIX_PROMPT = "verify_fix.md"


def load_prompt_template(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def analysis_prompt_for_branch(target_branch: str) -> str:
    if target_branch == "0.15":
        return load_prompt_template(ANALYZE_015_PROMPT)

    return load_prompt_template(ANALYZE_MASTER_PROMPT)
