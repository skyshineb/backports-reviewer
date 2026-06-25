from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backport_harness.storage import ReportDecision, ReportPullRequest, connect
from backport_harness.storage import get_report_data


BACKPORT_CANDIDATE_DECISIONS = {
    "TARGET_BRANCH_BUGFIX",
    "SOURCE_POSSIBLY_APPLICABLE",
    "SOURCE_REPRODUCED_ON_TARGET",
    "SOURCE_FIX_VERIFIED_ON_TARGET",
    "NEEDS_HUMAN_REVIEW",
}
INCONCLUSIVE_DECISIONS = {
    "INCONCLUSIVE",
    "FAILED_INFRA",
    "NEEDS_RETRY",
}
DISCARDED_DECISIONS = {
    "SOURCE_NOT_APPLICABLE",
    "DISCARDED_NON_BUGFIX",
    "DISCARDED_DOCS_ONLY",
    "DISCARDED_CI_ONLY",
    "DISCARDED_RELEASE_ONLY",
}

BACKPORT_CANDIDATES_FILENAME = "backport-candidates.md"
INCONCLUSIVE_FILENAME = "inconclusive.md"
DISCARDED_FILENAME = "discarded.jsonl"
FULL_AUDIT_FILENAME = "full-audit.jsonl"


@dataclass(frozen=True)
class ReportGenerationResult:
    output_dir: Path
    backport_candidates_path: Path
    inconclusive_path: Path
    discarded_path: Path
    full_audit_path: Path
    backport_candidates_count: int
    inconclusive_count: int
    discarded_count: int
    full_audit_count: int


@dataclass(frozen=True)
class CategorizedReportRows:
    all_rows: list[ReportPullRequest]
    candidates: list[ReportPullRequest]
    inconclusive: list[ReportPullRequest]
    discarded: list[ReportPullRequest]


def generate_reports(*, sqlite_path: Path, output_dir: Path) -> ReportGenerationResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    categories = categorize_report_rows(load_report_rows(sqlite_path))

    backport_candidates_path = output_dir / BACKPORT_CANDIDATES_FILENAME
    inconclusive_path = output_dir / INCONCLUSIVE_FILENAME
    discarded_path = output_dir / DISCARDED_FILENAME
    full_audit_path = output_dir / FULL_AUDIT_FILENAME

    backport_candidates_path.write_text(
        _render_candidate_markdown(categories.candidates),
        encoding="utf-8",
    )
    inconclusive_path.write_text(
        _render_inconclusive_markdown(categories.inconclusive),
        encoding="utf-8",
    )
    discarded_path.write_text(
        _render_jsonl(_discarded_json_object(row) for row in categories.discarded),
        encoding="utf-8",
    )
    full_audit_path.write_text(
        _render_jsonl(_full_audit_json_object(row) for row in categories.all_rows),
        encoding="utf-8",
    )

    return ReportGenerationResult(
        output_dir=output_dir,
        backport_candidates_path=backport_candidates_path,
        inconclusive_path=inconclusive_path,
        discarded_path=discarded_path,
        full_audit_path=full_audit_path,
        backport_candidates_count=len(categories.candidates),
        inconclusive_count=len(categories.inconclusive),
        discarded_count=len(categories.discarded),
        full_audit_count=len(categories.all_rows),
    )


def load_report_rows(sqlite_path: Path) -> list[ReportPullRequest]:
    if not sqlite_path.exists():
        return []

    with connect(sqlite_path) as connection:
        return get_report_data(connection)


def categorize_report_rows(
    pull_requests: list[ReportPullRequest],
) -> CategorizedReportRows:
    candidates = [
        pull_request
        for pull_request in pull_requests
        if latest_decision_value(pull_request) in BACKPORT_CANDIDATE_DECISIONS
    ]
    inconclusive = [
        pull_request
        for pull_request in pull_requests
        if is_inconclusive_report_row(pull_request)
    ]
    discarded = [
        pull_request
        for pull_request in pull_requests
        if latest_decision_value(pull_request) in DISCARDED_DECISIONS
    ]
    return CategorizedReportRows(
        all_rows=pull_requests,
        candidates=candidates,
        inconclusive=inconclusive,
        discarded=discarded,
    )


def report_rows_for_view(
    categories: CategorizedReportRows,
    *,
    view: str,
) -> list[ReportPullRequest]:
    if view == "summary":
        return categories.all_rows
    if view == "candidates":
        return categories.candidates
    if view == "inconclusive":
        return categories.inconclusive
    if view == "discarded":
        return categories.discarded
    if view == "audit":
        return categories.all_rows
    raise ValueError(f"Unknown report view: {view}")


def filter_report_rows(
    rows: list[ReportPullRequest],
    *,
    decision: str | None = None,
    queue_status: str | None = None,
    review_status: str | None = None,
    limit: int | None = None,
) -> list[ReportPullRequest]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive.")

    filtered = []
    for row in rows:
        if decision is not None and report_decision_label(row) != decision:
            continue
        if queue_status is not None and row.queue_status != queue_status:
            continue
        if review_status is not None and human_review_status(row) != review_status:
            continue
        filtered.append(row)

    if limit is not None:
        return filtered[:limit]
    return filtered


def latest_decision_value(pull_request: ReportPullRequest) -> str | None:
    if pull_request.latest_decision is None:
        return None
    return pull_request.latest_decision.decision


def report_decision_label(pull_request: ReportPullRequest) -> str:
    return latest_decision_value(pull_request) or pull_request.queue_status or "-"


def report_decision_confidence(pull_request: ReportPullRequest) -> str:
    return _latest_decision_field(pull_request, "confidence")


def report_decision_reason(pull_request: ReportPullRequest) -> str:
    return _latest_decision_field(pull_request, "reason")


def report_human_action(pull_request: ReportPullRequest) -> str:
    return _latest_decision_field(pull_request, "human_action")


def report_evidence_summary(decision: ReportDecision | None) -> str:
    return _evidence_summary(decision)


def human_review_status(pull_request: ReportPullRequest) -> str:
    return _human_review_status(pull_request)


def is_inconclusive_report_row(pull_request: ReportPullRequest) -> bool:
    decision = latest_decision_value(pull_request)
    if decision in INCONCLUSIVE_DECISIONS:
        return True
    return decision is None and pull_request.queue_status in {
        "FAILED_INFRA",
        "NEEDS_RETRY",
    }


def _render_candidate_markdown(pull_requests: list[ReportPullRequest]) -> str:
    columns = [
        "PR",
        "Upstream branch",
        "Merged date",
        "Decision",
        "Confidence",
        "Summary",
        "Evidence summary",
        "Human action",
        "Human review status",
    ]
    return _render_markdown_report(
        title="Backport Candidates",
        empty_message="No backport candidates found.",
        columns=columns,
        rows=[
            [
                _markdown_pr_link(pull_request),
                pull_request.upstream_branch,
                pull_request.merged_at,
                latest_decision_value(pull_request) or "-",
                _latest_decision_field(pull_request, "confidence"),
                _latest_decision_field(pull_request, "reason"),
                _evidence_summary(pull_request.latest_decision),
                _latest_decision_field(pull_request, "human_action"),
                _human_review_status(pull_request),
            ]
            for pull_request in pull_requests
        ],
    )


def _render_inconclusive_markdown(pull_requests: list[ReportPullRequest]) -> str:
    columns = [
        "PR",
        "Upstream branch",
        "Merged date",
        "Decision",
        "Confidence",
        "Summary",
        "Evidence summary",
        "Human action",
        "Human review status",
    ]
    return _render_markdown_report(
        title="Inconclusive",
        empty_message="No inconclusive PRs found.",
        columns=columns,
        rows=[
            [
                _markdown_pr_link(pull_request),
                pull_request.upstream_branch,
                pull_request.merged_at,
                latest_decision_value(pull_request) or pull_request.queue_status or "-",
                _latest_decision_field(pull_request, "confidence"),
                _latest_decision_field(pull_request, "reason"),
                _evidence_summary(pull_request.latest_decision),
                _latest_decision_field(pull_request, "human_action"),
                _human_review_status(pull_request),
            ]
            for pull_request in pull_requests
        ],
    )


def _render_markdown_report(
    *,
    title: str,
    empty_message: str,
    columns: list[str],
    rows: list[list[str]],
) -> str:
    lines = [f"# {title}", ""]
    if not rows:
        lines.extend([empty_message, ""])
        return "\n".join(lines)

    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")
    lines.append("")
    return "\n".join(lines)


def _render_jsonl(objects: Any) -> str:
    lines = [json.dumps(item, sort_keys=True) for item in objects]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _discarded_json_object(pull_request: ReportPullRequest) -> dict[str, Any]:
    return {
        "pr": _pr_json_object(pull_request),
        "queue": _queue_json_object(pull_request),
        "latest_decision": _decision_json_object(pull_request.latest_decision),
        "human_review": _human_review_json_object(pull_request),
    }


def _full_audit_json_object(pull_request: ReportPullRequest) -> dict[str, Any]:
    return {
        "pr": _pr_json_object(pull_request),
        "queue": _queue_json_object(pull_request),
        "latest_decision": _decision_json_object(pull_request.latest_decision),
        "decisions": [
            _decision_json_object(decision) for decision in pull_request.decisions
        ],
        "human_review": _human_review_json_object(pull_request),
    }


def _pr_json_object(pull_request: ReportPullRequest) -> dict[str, Any]:
    return {
        "number": pull_request.github_pr_number,
        "url": pull_request.github_pr_url,
        "title": pull_request.title,
        "upstream_branch": pull_request.upstream_branch,
        "merged_at": pull_request.merged_at,
    }


def _queue_json_object(pull_request: ReportPullRequest) -> dict[str, Any]:
    return {
        "status": pull_request.queue_status,
        "priority": pull_request.priority,
        "attempts": pull_request.attempts,
    }


def _decision_json_object(decision: ReportDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None

    return {
        "id": decision.id,
        "analysis_run_id": decision.analysis_run_id,
        "run_id": decision.run_id,
        "decision": decision.decision,
        "confidence": decision.confidence,
        "bugfix_classification": decision.bugfix_classification,
        "applies_to_target_ref": decision.applies_to_target_ref,
        "reason": decision.reason,
        "human_action": decision.human_action,
        "created_at": decision.created_at,
        "evidence": [
            {
                "type": evidence.evidence_type,
                "description": evidence.description,
                "file_path": evidence.file_path,
                "command": evidence.command,
                "exit_code": evidence.exit_code,
                "log_path": evidence.log_path,
                "patch_path": evidence.patch_path,
            }
            for evidence in decision.evidence
        ],
    }


def _human_review_json_object(
    pull_request: ReportPullRequest,
) -> dict[str, Any] | None:
    if pull_request.human_review is None:
        return None

    return {
        "status": pull_request.human_review.status,
        "reviewer": pull_request.human_review.reviewer,
        "comment": pull_request.human_review.comment,
        "updated_at": pull_request.human_review.updated_at,
    }


def _latest_decision_field(pull_request: ReportPullRequest, field_name: str) -> str:
    if pull_request.latest_decision is None:
        return "-"
    value = getattr(pull_request.latest_decision, field_name)
    return str(value) if value else "-"


def _evidence_summary(decision: ReportDecision | None) -> str:
    if decision is None or not decision.evidence:
        return "-"
    return "; ".join(evidence.description for evidence in decision.evidence)


def _human_review_status(pull_request: ReportPullRequest) -> str:
    if pull_request.human_review is None:
        return "-"
    return pull_request.human_review.status


def _markdown_pr_link(pull_request: ReportPullRequest) -> str:
    return f"[#{pull_request.github_pr_number}]({pull_request.github_pr_url})"


def _markdown_cell(value: str) -> str:
    normalized = value.replace("\n", " ").replace("\r", " ")
    return normalized.replace("|", "\\|")
