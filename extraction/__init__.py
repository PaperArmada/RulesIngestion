"""
Stage A extraction: PDF → MarkerStream → Chunk[].

Document identity (A-DOC): one Logical Document per (ruleset_id, book_id); provenance on every Chunk.
Public API: run_extraction, MarkerBlock, Chunk, DropRecord, ExtractionResult, LogicalDocument, DocumentPart.
"""

from extraction.chunker import ExtractionResult
from extraction.run import run_extraction
from extraction.schemas import Chunk, DocumentPart, DropRecord, LogicalDocument, MarkerBlock

__all__ = [
    "Chunk",
    "DocumentPart",
    "DropRecord",
    "ExtractionResult",
    "LogicalDocument",
    "MarkerBlock",
    "run_extraction",
]
