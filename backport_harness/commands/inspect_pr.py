from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backport_harness.storage import InspectedPullRequest, connect
from backport_harness.storage import get_pull_request_inspection


def render_inspect_pr(
    *,
    sqlite_path: Path,
    pr_number: int,
    console: Console | None = None,
) -> None:
    console = console or Console(width=160)

    if not sqlite_path.exists():
        raise typer.BadParameter(f"No saved PR found for #{pr_number}.")

    with connect(sqlite_path) as connection:
        pull_request = get_pull_request_inspection(
            connection,
            pr_number=pr_number,
        )

    if pull_request is None:
        raise typer.BadParameter(f"No saved PR found for #{pr_number}.")

    _render_pull_request(console, pull_request)
    _render_files(console, pull_request)
    _render_decision(console, pull_request)
    _render_analysis_run(console, pull_request)
    _render_test_runs(console, pull_request)
    _render_human_review(console, pull_request)


def _render_pull_request(
    console: Console,
    pull_request: InspectedPullRequest,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("PR", f"#{pull_request.github_pr_number}")
    table.add_row("Title", pull_request.title)
    table.add_row("URL", pull_request.github_pr_url)
    table.add_row("Upstream branch", pull_request.upstream_branch)
    table.add_row("Source branch", pull_request.source_branch or "-")
    table.add_row("Merged commit", pull_request.merged_commit_sha or "-")
    table.add_row("Merged at", pull_request.merged_at)
    table.add_row("Author", pull_request.author or "-")

    if pull_request.queue is None:
        table.add_row("Queue", "-")
    else:
        table.add_row("Queue status", pull_request.queue.status)
        table.add_row("Priority", str(pull_request.queue.priority))
        table.add_row("Attempts", str(pull_request.queue.attempts))
        table.add_row("Next retry", pull_request.queue.next_retry_at or "-")
        table.add_row("Locked", _format_locked_state(pull_request))
        table.add_row("Last error", pull_request.queue.last_error or "-")

    console.print(Panel(table, title="Pull Request", expand=False))


def _render_files(console: Console, pull_request: InspectedPullRequest) -> None:
    if not pull_request.files:
        console.print(Panel("No changed files recorded.", title="Changed Files"))
        return

    table = Table(title="Changed Files")
    table.add_column("File")
    table.add_column("Status", no_wrap=True)
    table.add_column("Add", justify="right", no_wrap=True)
    table.add_column("Del", justify="right", no_wrap=True)
    table.add_column("Flags", no_wrap=True)

    for changed_file in pull_request.files:
        flags = []
        if changed_file.is_test_file:
            flags.append("test")
        if changed_file.is_docs_file:
            flags.append("docs")
        if changed_file.is_ci_file:
            flags.append("ci")

        table.add_row(
            changed_file.filename,
            changed_file.status or "-",
            _format_optional_int(changed_file.additions),
            _format_optional_int(changed_file.deletions),
            ", ".join(flags) if flags else "-",
        )

    console.print(table)


def _render_decision(console: Console, pull_request: InspectedPullRequest) -> None:
    if pull_request.latest_decision is None:
        console.print(Panel("No decision recorded yet.", title="Latest Decision"))
        return

    decision = pull_request.latest_decision
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Decision", decision.decision)
    table.add_row("Confidence", decision.confidence)
    table.add_row("Bugfix class", decision.bugfix_classification or "-")
    table.add_row("Applies to target ref", _format_optional_bool(decision.applies_to_target_ref))
    table.add_row("Reason", decision.reason)
    table.add_row("Human action", decision.human_action or "-")
    table.add_row("Created at", decision.created_at)
    console.print(Panel(table, title="Latest Decision", expand=False))

    _render_evidence(console, pull_request)


def _render_analysis_run(
    console: Console,
    pull_request: InspectedPullRequest,
) -> None:
    if pull_request.latest_analysis_run is None:
        console.print(Panel("No analysis run recorded.", title="Latest Analysis Run"))
        return

    analysis_run = pull_request.latest_analysis_run
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Run ID", analysis_run.run_id)
    table.add_row("Status", analysis_run.status)
    table.add_row("Started at", analysis_run.started_at)
    table.add_row("Finished at", analysis_run.finished_at or "-")
    table.add_row("Codex exit", _format_optional_int(analysis_run.codex_exit_code))
    table.add_row("Task dir", analysis_run.task_dir)
    table.add_row("Result JSON", analysis_run.result_json_path or "-")
    table.add_row("Notes", analysis_run.notes_path or "-")
    table.add_row("Stdout log", analysis_run.stdout_log_path or "-")
    table.add_row("Stderr log", analysis_run.stderr_log_path or "-")
    console.print(Panel(table, title="Latest Analysis Run", expand=False))


def _render_evidence(console: Console, pull_request: InspectedPullRequest) -> None:
    if not pull_request.evidence:
        console.print(Panel("No evidence recorded.", title="Evidence"))
        return

    table = Table(title="Evidence")
    table.add_column("Type", no_wrap=True)
    table.add_column("Description")
    table.add_column("File")
    table.add_column("Command")
    table.add_column("Exit", justify="right", no_wrap=True)
    table.add_column("Log")
    table.add_column("Patch")

    for evidence in pull_request.evidence:
        table.add_row(
            evidence.evidence_type,
            evidence.description,
            evidence.file_path or "-",
            evidence.command or "-",
            _format_optional_int(evidence.exit_code),
            evidence.log_path or "-",
            evidence.patch_path or "-",
        )

    console.print(table)


def _render_test_runs(console: Console, pull_request: InspectedPullRequest) -> None:
    if not pull_request.test_runs:
        console.print(Panel("No test runs recorded.", title="Test Runs"))
        return

    table = Table(title="Test Runs")
    table.add_column("Phase", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Exit", justify="right", no_wrap=True)
    table.add_column("Command")
    table.add_column("Log")

    for test_run in pull_request.test_runs:
        table.add_row(
            test_run.phase,
            test_run.result,
            _format_optional_int(test_run.exit_code),
            test_run.command or "-",
            test_run.log_path or "-",
        )

    console.print(table)


def _render_human_review(
    console: Console,
    pull_request: InspectedPullRequest,
) -> None:
    if pull_request.human_review is None:
        console.print(Panel("No human review recorded.", title="Human Review"))
        return

    review = pull_request.human_review
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Status", review.status)
    table.add_row("Reviewer", review.reviewer or "-")
    table.add_row("Comment", review.comment or "-")
    table.add_row("Updated at", review.updated_at)
    console.print(Panel(table, title="Human Review", expand=False))


def _format_locked_state(pull_request: InspectedPullRequest) -> str:
    if pull_request.queue is None or pull_request.queue.locked_at is None:
        return "-"

    if pull_request.queue.locked_by is None:
        return pull_request.queue.locked_at

    return f"{pull_request.queue.locked_at} by {pull_request.queue.locked_by}"


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def _format_optional_int(value: int | None) -> str:
    if value is None:
        return "-"
    return str(value)
