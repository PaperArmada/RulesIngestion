"""
Stage A extraction — Mark III placeholder.

Marker-centric extraction (PDF → MarkerStream → Chunk[]) has been moved to
Archive/marker-era/extraction/. That pipeline is not normative for Mark III.

Mark III Stage A will produce prose (authored text) with textual provenance;
see Docs/Design/STAGE_A_PROSE_RECONSTRUCTION.md and RULES_INGESTION_MARK_III_OVERVIEW.md.

To run the archived Marker-era pipeline from repo root:

  PYTHONPATH=Archive/marker-era uv run python -m extraction.run <pdf_path> --output-dir <dir> ...
"""

__all__: list[str] = []
