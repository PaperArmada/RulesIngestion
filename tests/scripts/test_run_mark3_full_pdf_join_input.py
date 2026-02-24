from __future__ import annotations

import json
from pathlib import Path

from scripts.run_mark3_full_pdf import _load_units_by_page_from_artifacts


def _write_stage_b_units(page_dir: Path, unit_id: str) -> None:
    page_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "units": [
            {
                "unit_id": unit_id,
                "unit_type": "prose",
                "text": f"text-{unit_id}",
                "structural_path": [],
                "ordering_key": 0,
                "page_fingerprint": f"fp-{unit_id}",
                "content_hash": f"h-{unit_id}",
                "source_line_start": 0,
                "source_line_end": 1,
                "anomaly_flags": [],
                "content_version": "v",
            }
        ]
    }
    (page_dir / "stageB.evidence_units.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def test_load_units_by_page_from_artifacts_ignores_summary_state(tmp_path: Path) -> None:
    stem = "My Book"
    out_base = tmp_path / stem
    # Out-of-order creation to verify sort by page index.
    _write_stage_b_units(out_base / f"{stem}_p11", "u11")
    _write_stage_b_units(out_base / f"{stem}_p2", "u2")
    # A pipeline summary with null stage payload should not affect join input.
    (out_base / "run_summary.json").write_text(
        json.dumps(
            [
                {"label": f"{stem}_p2", "stage_a": None, "stage_b": None, "error": None},
                {"label": f"{stem}_p11", "stage_a": None, "stage_b": None, "error": None},
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    units_by_page, manifest = _load_units_by_page_from_artifacts(out_base, stem)
    assert len(units_by_page) == 2
    assert [m["label"] for m in manifest] == [f"{stem}_p2", f"{stem}_p11"]
    assert [page_units[0].unit_id for page_units in units_by_page] == ["u2", "u11"]
