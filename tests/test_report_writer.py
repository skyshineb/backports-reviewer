import json
from pathlib import Path

from backport_harness.report_writer import generate_reports
from backport_harness.storage import connect, init_database, store_human_review


def test_generate_reports_creates_empty_reports_for_missing_database(
    tmp_path: Path,
) -> None:
    result = generate_reports(
        sqlite_path=tmp_path / "missing.sqlite3",
        output_dir=tmp_path / "reports",
    )

    assert result.backport_candidates_count == 0
    assert result.inconclusive_count == 0
    assert result.discarded_count == 0
    assert result.full_audit_count == 0
    assert "No backport candidates found." in result.backport_candidates_path.read_text(
        encoding="utf-8"
    )
    assert "No inconclusive PRs found." in result.inconclusive_path.read_text(
        encoding="utf-8"
    )
    assert result.discarded_path.read_text(encoding="utf-8") == ""
    assert result.full_audit_path.read_text(encoding="utf-8") == ""


def test_generate_reports_places_prs_in_expected_categories(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        candidate_pr_id = _insert_saved_pr(
            connection,
            number=1,
            title="Possibly applicable fix",
            branch="master",
            status="REPORTABLE",
        )
        candidate_run_id = _insert_analysis_run(connection, pr_id=candidate_pr_id)
        candidate_decision_id = _insert_decision(
            connection,
            pr_id=candidate_pr_id,
            analysis_run_id=candidate_run_id,
            decision="SOURCE_POSSIBLY_APPLICABLE",
            reason="Relevant 0.15 logic exists without test proof",
            human_action="Review public OSS applicability",
            created_at="2024-01-01T00:10:00Z",
        )
        _insert_evidence(
            connection,
            decision_id=candidate_decision_id,
            description="Matched public 0.15 code path",
        )
        _insert_human_review(connection, pr_id=candidate_pr_id, status="needs_review")

        inconclusive_pr_id = _insert_saved_pr(
            connection,
            number=2,
            title="Infra failed",
            branch="master",
            status="FAILED_INFRA",
        )
        inconclusive_run_id = _insert_analysis_run(connection, pr_id=inconclusive_pr_id)
        _insert_decision(
            connection,
            pr_id=inconclusive_pr_id,
            analysis_run_id=inconclusive_run_id,
            decision="FAILED_INFRA",
            reason="Test command timed out",
            created_at="2024-01-01T00:20:00Z",
        )

        retry_pr_id = _insert_saved_pr(
            connection,
            number=3,
            title="Needs retry",
            branch="master",
            status="NEEDS_RETRY",
        )
        _insert_analysis_run(connection, pr_id=retry_pr_id)

        queue_only_failed_pr_id = _insert_saved_pr(
            connection,
            number=5,
            title="Exhausted infra failure",
            branch="master",
            status="FAILED_INFRA",
        )
        _insert_analysis_run(connection, pr_id=queue_only_failed_pr_id)

        discarded_pr_id = _insert_saved_pr(
            connection,
            number=4,
            title="Docs only",
            branch="0.15",
            status="DONE",
        )
        discarded_run_id = _insert_analysis_run(connection, pr_id=discarded_pr_id)
        _insert_decision(
            connection,
            pr_id=discarded_pr_id,
            analysis_run_id=discarded_run_id,
            decision="DISCARDED_DOCS_ONLY",
            reason="Only docs changed",
            created_at="2024-01-01T00:30:00Z",
        )

    result = generate_reports(sqlite_path=sqlite_path, output_dir=tmp_path / "reports")

    candidates = result.backport_candidates_path.read_text(encoding="utf-8")
    inconclusive = result.inconclusive_path.read_text(encoding="utf-8")
    discarded = _read_jsonl(result.discarded_path)
    audit = _read_jsonl(result.full_audit_path)

    assert result.backport_candidates_count == 1
    assert "SOURCE_POSSIBLY_APPLICABLE" in candidates
    assert "Matched public 0.15 code path" in candidates
    assert "needs_review" in candidates
    assert result.inconclusive_count == 3
    assert "FAILED_INFRA" in inconclusive
    assert "NEEDS_RETRY" in inconclusive
    assert "[#5](https://github.com/apache/hudi/pull/5)" in inconclusive
    assert result.discarded_count == 1
    assert discarded[0]["latest_decision"]["decision"] == "DISCARDED_DOCS_ONLY"
    assert result.full_audit_count == 5
    assert {row["pr"]["number"] for row in audit} == {1, 2, 3, 4, 5}


def test_generate_reports_includes_command_created_human_review(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=1,
            title="Possibly applicable fix",
            branch="master",
            status="REPORTABLE",
        )
        analysis_run_id = _insert_analysis_run(connection, pr_id=pr_id)
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=analysis_run_id,
            decision="SOURCE_POSSIBLY_APPLICABLE",
            reason="Relevant 0.15 logic exists without test proof",
            created_at="2024-01-01T00:10:00Z",
        )
        store_human_review(
            connection,
            pr_number=1,
            status="accepted_for_backport",
            comment="Relevant to private fork",
        )

    result = generate_reports(sqlite_path=sqlite_path, output_dir=tmp_path / "reports")

    candidates = result.backport_candidates_path.read_text(encoding="utf-8")
    audit = _read_jsonl(result.full_audit_path)
    assert "accepted_for_backport" in candidates
    assert audit[0]["human_review"] == {
        "comment": "Relevant to private fork",
        "reviewer": None,
        "status": "accepted_for_backport",
        "updated_at": audit[0]["human_review"]["updated_at"],
    }


def test_full_audit_includes_all_decisions_and_evidence(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=123,
            title="Decision changed",
            branch="master",
            status="DONE",
        )
        first_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-1")
        second_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-2")
        first_decision_id = _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=first_run_id,
            decision="INCONCLUSIVE",
            reason="Missing proof",
            created_at="2024-01-01T00:10:00Z",
        )
        second_decision_id = _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=second_run_id,
            decision="SOURCE_NOT_APPLICABLE",
            reason="Code absent",
            created_at="2024-01-01T00:20:00Z",
        )
        _insert_evidence(connection, decision_id=first_decision_id, description="unclear")
        _insert_evidence(connection, decision_id=second_decision_id, description="absent")

    result = generate_reports(sqlite_path=sqlite_path, output_dir=tmp_path / "reports")
    audit = _read_jsonl(result.full_audit_path)

    assert audit[0]["latest_decision"]["decision"] == "SOURCE_NOT_APPLICABLE"
    assert [row["decision"] for row in audit[0]["decisions"]] == [
        "INCONCLUSIVE",
        "SOURCE_NOT_APPLICABLE",
    ]
    assert audit[0]["decisions"][0]["evidence"][0]["description"] == "unclear"
    assert audit[0]["decisions"][1]["evidence"][0]["description"] == "absent"
    assert (
        audit[0]["decisions"][1]["evidence"][0]["patch_path"]
        == "output/patches/adapted-fix.patch"
    )


def test_generate_reports_overwrites_stale_content_after_decision_changes(
    tmp_path: Path,
) -> None:
    sqlite_path = tmp_path / "backport_harness.sqlite3"
    output_dir = tmp_path / "reports"
    init_database(sqlite_path)

    with connect(sqlite_path) as connection:
        pr_id = _insert_saved_pr(
            connection,
            number=123,
            title="Changed classification",
            branch="master",
            status="REPORTABLE",
        )
        first_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-1")
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=first_run_id,
            decision="TARGET_BRANCH_BUGFIX",
            reason="Direct release fix",
            created_at="2024-01-01T00:10:00Z",
        )

    generate_reports(sqlite_path=sqlite_path, output_dir=output_dir)
    assert "TARGET_BRANCH_BUGFIX" in (output_dir / "backport-candidates.md").read_text(
        encoding="utf-8"
    )

    with connect(sqlite_path) as connection:
        second_run_id = _insert_analysis_run(connection, pr_id=pr_id, run_id="run-2")
        _insert_decision(
            connection,
            pr_id=pr_id,
            analysis_run_id=second_run_id,
            decision="DISCARDED_NON_BUGFIX",
            reason="Not a bugfix",
            created_at="2024-01-01T00:20:00Z",
        )

    generate_reports(sqlite_path=sqlite_path, output_dir=output_dir)

    assert "TARGET_BRANCH_BUGFIX" not in (
        output_dir / "backport-candidates.md"
    ).read_text(encoding="utf-8")
    discarded = _read_jsonl(output_dir / "discarded.jsonl")
    assert discarded[0]["latest_decision"]["decision"] == "DISCARDED_NON_BUGFIX"


def _read_jsonl(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8")
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines()]


def _insert_saved_pr(
    connection,
    *,
    number: int,
    title: str,
    branch: str,
    status: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO prs(
            github_pr_number,
            github_pr_url,
            title,
            upstream_branch,
            merged_at,
            created_in_db_at,
            updated_in_db_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            number,
            f"https://github.com/apache/hudi/pull/{number}",
            title,
            branch,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    pr_id = int(cursor.lastrowid)
    connection.execute(
        """
        INSERT INTO analysis_queue(
            pr_id,
            status,
            priority,
            attempts,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (pr_id, status, 50, 1, "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    )
    return pr_id


def _insert_analysis_run(connection, *, pr_id: int, run_id: str = "run-1") -> int:
    cursor = connection.execute(
        """
        INSERT INTO analysis_runs(
            pr_id,
            run_id,
            started_at,
            finished_at,
            codex_exit_code,
            status,
            task_dir
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            run_id,
            "2024-01-01T00:00:00Z",
            "2024-01-01T00:10:00Z",
            0,
            "DONE",
            f"workspace/tasks/pr-{pr_id}",
        ),
    )
    return int(cursor.lastrowid)


def _insert_decision(
    connection,
    *,
    pr_id: int,
    analysis_run_id: int,
    decision: str,
    reason: str,
    created_at: str,
    human_action: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO decisions(
            pr_id,
            analysis_run_id,
            decision,
            confidence,
            bugfix_classification,
            applies_to_target_ref,
            reason,
            human_action,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            analysis_run_id,
            decision,
            "medium",
            "bugfix",
            1,
            reason,
            human_action,
            created_at,
        ),
    )
    return int(cursor.lastrowid)


def _insert_evidence(connection, *, decision_id: int, description: str) -> None:
    connection.execute(
        """
        INSERT INTO evidence(
            decision_id,
            evidence_type,
            description,
            file_path,
            command,
            exit_code,
            log_path,
            patch_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            "logic_match",
            description,
            "src/main/Hoodie.java",
            "mvn test",
            0,
            "workspace/tasks/pr-123/output/logs/test.log",
            "output/patches/adapted-fix.patch",
        ),
    )


def _insert_human_review(connection, *, pr_id: int, status: str) -> None:
    connection.execute(
        """
        INSERT INTO human_reviews(
            pr_id,
            status,
            reviewer,
            comment,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            pr_id,
            status,
            "reviewer",
            "Needs manual review",
            "2024-01-01T00:00:00Z",
        ),
    )
