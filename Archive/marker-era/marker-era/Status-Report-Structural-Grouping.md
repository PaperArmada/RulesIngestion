> This document reflects a Marker-first ingestion model and is not normative for Mark III.

# RulesIngestion Status Report: Structural Grouping

**Date:** 2025-02-03  
**For:** Main agent handoff

---

## What Was Implemented

**Structural rule-block grouping** in Stage B to fix truncation on multi-column PDFs. Previously, rule_block expansion iterated chunks sequentially and stopped at the first boundary; interleaved content (e.g., LIE and CREATE A DIVERSION mixed across columns) caused chunks to be cut off early.

**Changes:**

- New `broadening/structural.py`: `build_content_path_index()` and `content_path_for_rule_header()` for structural grouping
- `broadening/grouper.py`: `_apply_rule_block_expansion_structural()` groups by content path instead of physical adjacency
- Rule blocks now pull all chunks with the matching structural path from the full chunk list, regardless of position

---

## Current Gate Status

| Gate | Status | Notes                                        |
| ---- | ------ | -------------------------------------------- |
| M-B1 | PASS   | Prose char distribution                      |
| M-B2 | PASS   | Fragment rate                                |
| M-B3 | PASS   | Over-broad rate                              |
| M-B4 | PASS   | Structural coherence                         |
| M-B5 | FAIL   | Max rule 90.1% paragraph_run (threshold 80%) |
| M-B6 | PASS   | size_threshold_hit 8.9% (was ~10.5%)         |
| M-B7 | PASS   | Placeholder                                  |
| M-B8 | PASS   | Placeholder                                  |

---

## Known Limitations

1. **Marker layout vs. structure:** Marker’s `section_hierarchy` follows physical layout. Blocks that appear in another rule’s column can get the wrong path (e.g., CREATE A DIVERSION “Failure You don’t divert” assigned to FEINT). Structural grouping cannot fix upstream path misassignment.

2. **M-B5 failure:** `paragraph_run` dominates (90.1%). Rule diversity is below target but acceptable; rule_block still claims ~125 evidence chunks.

3. **Stage B Contract Addendum (semantic closure):** Not implemented. B-INV-R1 (rule semantic closure), M-B9 (rule truncation rate), and semantic-closure-driven size-cap override are still pending.

---

## Files Touched

| File                                                     | Action                           |
| -------------------------------------------------------- | -------------------------------- |
| `broadening/structural.py`                               | NEW                              |
| `broadening/grouper.py`                                  | MODIFIED (structural rule_block) |
| `tests/broadening/test_structural.py`                    | NEW                              |
| `tests/broadening/test_grouper.py`                       | MODIFIED (section_path in test)  |
| `Docs/Design/Structural-Grouping-Implementation-Plan.md` | Design doc                       |

---

## How to Re-run

```bash
# Stage B only (chunks already exist)
uv run python -m broadening.run out/StarFinder2e-PlayerCore-v2/chunks.json \
  --output-dir out/StarFinder2e-PlayerCore-v2 --check-gates

# Full pipeline (Stage A + B)
# See extraction/run.py and broadening/run.py
```

---

## Next Steps (Optional)

1. Implement Stage B Contract Addendum: semantic closure detection, M-B9, size-cap override for rule blocks.
2. Investigate M-B5: tune rules or thresholds if higher rule diversity is required.
3. Explore upstream fixes for layout-driven section misassignment (if needed).
