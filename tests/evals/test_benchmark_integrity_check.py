from __future__ import annotations

import json

from evals.v1_baseline.benchmark_integrity_check import (
    _duplicate_unit_ids,
    _scan_stage_b_gate_artifacts,
)


def test_duplicate_unit_ids_reports_repeated_ids() -> None:
    corpus = [
        {"id": "u-1", "text": "alpha"},
        {"id": "u-2", "text": "beta"},
        {"id": "u-1", "text": "gamma"},
        {"id": "", "text": "ignored"},
    ]

    assert _duplicate_unit_ids(corpus) == [{"unit_id": "u-1", "count": 2}]


def test_scan_stage_b_gate_artifacts_reports_failures_and_missing_files(tmp_path) -> None:
    ok_page = tmp_path / "TestDoc_p1"
    ok_page.mkdir()
    (ok_page / "stageB.evidence_units.json").write_text(json.dumps({"units": []}), encoding="utf-8")
    (ok_page / "stageB.gate_diagnostics.json").write_text(
        json.dumps([{"gate_name": "orphan", "passed": True, "detail": {}}]),
        encoding="utf-8",
    )

    failing_page = tmp_path / "TestDoc_p2"
    failing_page.mkdir()
    (failing_page / "stageB.evidence_units.json").write_text(json.dumps({"units": []}), encoding="utf-8")
    (failing_page / "stageB.gate_diagnostics.json").write_text(
        json.dumps([{"gate_name": "unit_size", "passed": False, "detail": {"oversized": 1}}]),
        encoding="utf-8",
    )

    missing_diag_page = tmp_path / "TestDoc_p3"
    missing_diag_page.mkdir()
    (missing_diag_page / "stageB.evidence_units.json").write_text(json.dumps({"units": []}), encoding="utf-8")

    report = _scan_stage_b_gate_artifacts(tmp_path)

    assert report["pages_scanned"] == 3
    assert report["failed"] is True
    assert report["failed_gate_counts"] == {"unit_size": 1}
    assert len(report["failing_pages"]) == 1
    assert len(report["missing_gate_diagnostics"]) == 1
