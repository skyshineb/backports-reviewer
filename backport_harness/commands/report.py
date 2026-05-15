from __future__ import annotations

from pathlib import Path

from backport_harness.report_writer import ReportGenerationResult, generate_reports


def write_reports(*, sqlite_path: Path, output_dir: Path) -> ReportGenerationResult:
    return generate_reports(sqlite_path=sqlite_path, output_dir=output_dir)
