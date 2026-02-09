# Brutal Pages Metrics

## Stage A Metrics

- **Coverage**: AST text chars / raw markdown content chars (threshold >= 0.95)
- **Ordering sanity**: leaf node source_line_start is monotonically increasing (zero inversions)
- **Table parse**: every HTML `<table>` in raw markdown has a matching AST node with correct row count
- **Stability**: content_hash matches across repeated OCR runs (flagged, not fatal)

## Stage B Metrics

- **Orphan rate**: fraction of EvidenceUnits with empty structural_path
- **Bleed detection**: zero overlapping source line ranges between units
- **Table integrity**: all table units have balanced `<table>`/`</table>` tags and >= 1 `<tr>`
- **Unit size bounds**: zero units > 5000 chars (oversized = fail). Undersized < 20 chars: warning by default; **fail** when fraction of undersized units on page exceeds `undersized_fail_ratio` (default 1.0 = off). When enabled, prevents substrate from being dominated by non-evidential atoms (see Stage B contract).

## Stage C Metrics

- Evidence coverage
- Canonical drift
- Partition violations

## Salvage Score

Fraction of EvidenceUnits without fatal anomaly flags (currently: `oversized` is the only fatal flag).
