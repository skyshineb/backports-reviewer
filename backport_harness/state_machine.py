from __future__ import annotations


QUEUE_STATUS_QUEUED = "QUEUED_FOR_ANALYSIS"
QUEUE_STATUS_RUNNING = "CODEX_RUNNING"
QUEUE_STATUS_VALIDATED = "VALIDATED"
QUEUE_STATUS_DONE = "DONE"
QUEUE_STATUS_REPORTABLE = "REPORTABLE"
QUEUE_STATUS_NEEDS_RETRY = "NEEDS_RETRY"
QUEUE_STATUS_FAILED_INFRA = "FAILED_INFRA"
QUEUE_STATUS_PAUSED = "PAUSED"

ALL_QUEUE_STATUSES = {
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_RUNNING,
    QUEUE_STATUS_VALIDATED,
    QUEUE_STATUS_DONE,
    QUEUE_STATUS_REPORTABLE,
    QUEUE_STATUS_NEEDS_RETRY,
    QUEUE_STATUS_FAILED_INFRA,
    QUEUE_STATUS_PAUSED,
}

RETRYABLE_QUEUE_STATUSES = {
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_NEEDS_RETRY,
}

BUGFIX_TITLE_KEYWORDS = (
    "bug",
    "fix",
    "regression",
    "correctness",
    "npe",
    "null pointer",
    "race",
    "corruption",
    "data loss",
    "failure",
    "error",
    "exception",
    "crash",
)

AMBIGUOUS_FIX_TITLE_KEYWORDS = (
    "repair",
    "resolve",
    "handle",
    "avoid",
    "prevent",
)

PRIORITY_CONFIGURED_TARGET_BRANCH = 10
PRIORITY_LIKELY_SOURCE_BUGFIX = 20
PRIORITY_AMBIGUOUS_SOURCE_FIX = 50
PRIORITY_DEFAULT = 100

ALLOWED_QUEUE_TRANSITIONS = {
    QUEUE_STATUS_QUEUED: {
        QUEUE_STATUS_RUNNING,
        QUEUE_STATUS_PAUSED,
    },
    QUEUE_STATUS_RUNNING: {
        QUEUE_STATUS_VALIDATED,
        QUEUE_STATUS_DONE,
        QUEUE_STATUS_REPORTABLE,
        QUEUE_STATUS_NEEDS_RETRY,
        QUEUE_STATUS_FAILED_INFRA,
    },
    QUEUE_STATUS_VALIDATED: {
        QUEUE_STATUS_DONE,
        QUEUE_STATUS_REPORTABLE,
        QUEUE_STATUS_NEEDS_RETRY,
        QUEUE_STATUS_FAILED_INFRA,
    },
    QUEUE_STATUS_NEEDS_RETRY: {
        QUEUE_STATUS_QUEUED,
        QUEUE_STATUS_RUNNING,
        QUEUE_STATUS_FAILED_INFRA,
        QUEUE_STATUS_PAUSED,
    },
    QUEUE_STATUS_FAILED_INFRA: {
        QUEUE_STATUS_QUEUED,
        QUEUE_STATUS_PAUSED,
    },
    QUEUE_STATUS_PAUSED: {
        QUEUE_STATUS_QUEUED,
    },
    QUEUE_STATUS_DONE: set(),
    QUEUE_STATUS_REPORTABLE: set(),
}


def assign_initial_priority(
    upstream_branch: str,
    title: str,
    *,
    target_ref_label: str | None = None,
) -> int:
    if target_ref_label is not None and upstream_branch == target_ref_label:
        return PRIORITY_CONFIGURED_TARGET_BRANCH

    normalized_title = title.lower()
    if _contains_any(normalized_title, BUGFIX_TITLE_KEYWORDS):
        return PRIORITY_LIKELY_SOURCE_BUGFIX

    if _contains_any(normalized_title, AMBIGUOUS_FIX_TITLE_KEYWORDS):
        return PRIORITY_AMBIGUOUS_SOURCE_FIX

    return PRIORITY_DEFAULT


def is_allowed_transition(from_status: str, to_status: str) -> bool:
    _validate_known_status(from_status)
    _validate_known_status(to_status)
    return to_status in ALLOWED_QUEUE_TRANSITIONS[from_status]


def validate_transition(from_status: str, to_status: str) -> None:
    if not is_allowed_transition(from_status, to_status):
        raise ValueError(
            f"Queue transition from {from_status} to {to_status} is not allowed."
        )


def _validate_known_status(status: str) -> None:
    if status not in ALL_QUEUE_STATUSES:
        raise ValueError(f"Unknown queue status: {status}")


def _contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)
