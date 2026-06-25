import pytest

from backport_harness.state_machine import (
    QUEUE_STATUS_DONE,
    QUEUE_STATUS_FAILED_INFRA,
    QUEUE_STATUS_NEEDS_RETRY,
    QUEUE_STATUS_PAUSED,
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_REPORTABLE,
    QUEUE_STATUS_RUNNING,
    QUEUE_STATUS_VALIDATED,
    assign_initial_priority,
    is_allowed_transition,
    validate_transition,
)


def test_queue_transitions_allow_expected_paths() -> None:
    assert is_allowed_transition(QUEUE_STATUS_QUEUED, QUEUE_STATUS_RUNNING)
    assert is_allowed_transition(QUEUE_STATUS_RUNNING, QUEUE_STATUS_VALIDATED)
    assert is_allowed_transition(QUEUE_STATUS_VALIDATED, QUEUE_STATUS_REPORTABLE)
    assert is_allowed_transition(QUEUE_STATUS_VALIDATED, QUEUE_STATUS_DONE)
    assert is_allowed_transition(QUEUE_STATUS_RUNNING, QUEUE_STATUS_DONE)
    assert is_allowed_transition(QUEUE_STATUS_RUNNING, QUEUE_STATUS_REPORTABLE)
    assert is_allowed_transition(QUEUE_STATUS_RUNNING, QUEUE_STATUS_NEEDS_RETRY)
    assert is_allowed_transition(QUEUE_STATUS_RUNNING, QUEUE_STATUS_FAILED_INFRA)
    assert is_allowed_transition(QUEUE_STATUS_NEEDS_RETRY, QUEUE_STATUS_QUEUED)
    assert is_allowed_transition(QUEUE_STATUS_PAUSED, QUEUE_STATUS_QUEUED)


def test_queue_transitions_reject_terminal_or_invalid_paths() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        validate_transition(QUEUE_STATUS_DONE, QUEUE_STATUS_RUNNING)

    with pytest.raises(ValueError, match="not allowed"):
        validate_transition(QUEUE_STATUS_REPORTABLE, QUEUE_STATUS_RUNNING)

    with pytest.raises(ValueError, match="Unknown queue status"):
        validate_transition("UNKNOWN", QUEUE_STATUS_RUNNING)


def test_assign_initial_priority_for_configured_target_branch() -> None:
    assert (
        assign_initial_priority(
            "release",
            "Add new feature",
            target_ref_label="release",
        )
        == 10
    )


def test_assign_initial_priority_for_likely_source_bugfix() -> None:
    assert assign_initial_priority("main", "Fix NPE in compaction") == 20
    assert assign_initial_priority("main", "Resolve data loss error") == 20


def test_assign_initial_priority_for_ambiguous_source_fix() -> None:
    assert assign_initial_priority("main", "Avoid stale metadata table state") == 50


def test_assign_initial_priority_default() -> None:
    assert assign_initial_priority("main", "Add new config option") == 100
