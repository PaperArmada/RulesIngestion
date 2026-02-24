from __future__ import annotations

import json
from pathlib import Path

from scripts.check_join_integrity import build_integrity_report


def test_build_integrity_report_counts_source_unit_ids_as_represented(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    page_dir = run_dir / "Doc_p0"
    page_dir.mkdir(parents=True, exist_ok=True)

    stage_b = {
        "units": [
            {
                "unit_id": "u1",
                "unit_type": "prose",
                "text": "A",
                "structural_path": [],
                "ordering_key": 0,
                "page_fingerprint": "fp0",
                "content_hash": "h1",
                "source_line_start": 0,
                "source_line_end": 1,
                "anomaly_flags": [],
                "content_version": "v",
            },
            {
                "unit_id": "u2",
                "unit_type": "prose",
                "text": "B",
                "structural_path": [],
                "ordering_key": 1,
                "page_fingerprint": "fp0",
                "content_hash": "h2",
                "source_line_start": 1,
                "source_line_end": 2,
                "anomaly_flags": [],
                "content_version": "v",
            },
        ]
    }
    (page_dir / "stageB.evidence_units.json").write_text(json.dumps(stage_b), encoding="utf-8")

    joined = {
        "units": [
            {
                "unit_id": "u1",
                "unit_type": "prose",
                "text": "A B",
                "structural_path": [],
                "ordering_key": 0,
                "page_fingerprint": "fp0",
                "content_hash": "hx",
                "source_line_start": 0,
                "source_line_end": 2,
                "anomaly_flags": ["cross_page_join"],
                "content_version": "v",
                "source_unit_ids": ["u1", "u2"],
            }
        ]
    }
    (run_dir / "joined.evidence_units.json").write_text(json.dumps(joined), encoding="utf-8")

    report = build_integrity_report(run_dir)
    assert report["summary"]["stageb_missing_unit_id_count"] == 0
    assert report["summary"]["pages_with_any_integrity_issue_count"] == 0
