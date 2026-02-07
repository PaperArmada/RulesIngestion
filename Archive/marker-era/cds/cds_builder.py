"""
CDS Builder v0.2 - Canonical Document Skeleton with Constraints

Builds the CDS payload structure containing:
- Document outline (chapters, sections)
- Chunk facts (observed only, no semantic inference)
- Constraint sets (admissibility and conflict rules)

This replaces the v0.1 "signals" approach with explicit constraints.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .chunk_facts_adapter import (
    build_chunk_facts,
    build_chunk_facts_index,
    _stable_section_id,
)
from .constraint_engine import compute_als_from_chunk_facts_dicts


# -------------------------
# Schema version
# -------------------------

CDS_SCHEMA_VERSION = "0.2"


# -------------------------
# Section hierarchy resolution
# -------------------------


def _build_header_id_mapping(chunks: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Build a mapping from header chunk ID suffixes to their text.

    section_hierarchy references use paths like '/page/1/SectionHeader/0'
    which correspond to chunk ID suffixes.
    """
    header_map: Dict[str, str] = {}

    for chunk in chunks:
        if chunk.get("block_type") != "SectionHeader":
            continue

        chunk_id = chunk.get("id", "")
        text = chunk.get("text", "").strip()

        if not chunk_id or not text:
            continue

        # Store by full ID and suffix
        header_map[chunk_id] = text

        # Extract suffix after '::' for reference matching
        if "::" in chunk_id:
            _, suffix = chunk_id.split("::", 1)
            header_map[suffix] = text

    return header_map


def _resolve_section_hierarchy(
    section_hierarchy: Dict[str, str],
    header_map: Dict[str, str],
) -> List[str]:
    """
    Resolve section_hierarchy references to actual header text.

    Args:
        section_hierarchy: Dict like {'1': '/page/5/SectionHeader/0', '2': '...'}
        header_map: Mapping from header ID/suffix to text

    Returns:
        List of section titles in order (top to bottom)
    """
    if not section_hierarchy:
        return []

    # Sort by level key (numeric string)
    sorted_levels = sorted(section_hierarchy.items(), key=lambda x: int(x[0]))

    path: List[str] = []
    for _level, ref in sorted_levels:
        text = header_map.get(ref, "")
        if text:
            # Clean up the text (remove ** markers, extra whitespace)
            text = text.replace("**", "").strip()
            if text:
                path.append(text)

    return path


def _get_resolved_section_path(
    chunk: Dict[str, Any],
    header_map: Dict[str, str],
) -> List[str]:
    """
    Get section path for a chunk, preferring explicit section_path
    but falling back to resolved section_hierarchy.
    """
    # First try explicit section_path
    section_path = chunk.get("section_path", [])
    if section_path:
        return section_path

    # Fall back to resolving section_hierarchy
    section_hierarchy = chunk.get("section_hierarchy", {})
    return _resolve_section_hierarchy(section_hierarchy, header_map)


# -------------------------
# Outline builders
# -------------------------


def _build_chapter_nodes(
    chunks: List[Dict[str, Any]],
    header_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Build chapter nodes from chunks.

    A chapter is the first element of section_path for each unique top-level section.
    """
    chapters: Dict[str, Dict[str, Any]] = {}
    chapter_ordinal = 0

    for chunk in chunks:
        section_path = _get_resolved_section_path(chunk, header_map)
        if not section_path:
            continue

        chapter_title = section_path[0]
        if chapter_title not in chapters:
            # Generate stable chapter ID
            chapter_hash = hashlib.sha256(
                chapter_title.encode("utf-8")
            ).hexdigest()[:12]
            chapter_id = f"ch_{chapter_hash}"

            chapters[chapter_title] = {
                "chapter_id": chapter_id,
                "title": chapter_title,
                "ordinal": chapter_ordinal,
            }
            chapter_ordinal += 1

    return list(chapters.values())


def _build_section_nodes(
    chunks: List[Dict[str, Any]],
    chapter_lookup: Dict[str, str],
    header_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Build section nodes from chunks.

    Each unique section_path becomes a section node.
    """
    sections: Dict[str, Dict[str, Any]] = {}
    section_ordinal = 0

    for chunk in chunks:
        section_path = _get_resolved_section_path(chunk, header_map)
        if not section_path:
            continue

        # Create stable section ID from full path
        section_id = _stable_section_id(section_path)

        if section_id not in sections:
            # Find chapter for this section
            chapter_title = section_path[0]
            chapter_id = chapter_lookup.get(chapter_title)

            sections[section_id] = {
                "section_id": section_id,
                "path": section_path,
                "ordinal": section_ordinal,
            }
            if chapter_id:
                sections[section_id]["chapter_id"] = chapter_id

            section_ordinal += 1

    return list(sections.values())


def _build_outline(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build document outline from chunks.

    Returns:
        {
            "chapters": [...],
            "sections": [...]
        }
    """
    # Build header ID -> text mapping for resolving section_hierarchy
    header_map = _build_header_id_mapping(chunks)

    chapters = _build_chapter_nodes(chunks, header_map)

    # Build chapter title -> id lookup
    chapter_lookup = {ch["title"]: ch["chapter_id"] for ch in chapters}

    sections = _build_section_nodes(chunks, chapter_lookup, header_map)

    return {
        "chapters": chapters,
        "sections": sections,
        "header_map_size": len(header_map),  # Diagnostic
    }


# -------------------------
# Constraint set builders
# -------------------------


def _build_admissibility_rules() -> List[Dict[str, Any]]:
    """
    Build the static list of admissibility rules.

    These rules are the same for all documents - they define
    how query intent maps to chunk admissibility.
    """
    return [
        {
            "rule_id": "A0_allow_explicit_examples_example_request",
            "version": 1,
            "description": "Example-only queries can allow explicitly labeled examples",
            "applies_when": {
                "query_intents": ["example_request"],
                "chunk_predicates": [
                    {
                        "field": "rhetoric_explicit.has_example_label",
                        "op": "is_true",
                        "value": None,
                    }
                ],
            },
            "decision": {"type": "ALLOW"},
            "provenance": {
                "derived_from": ["rhetoric_explicit.has_example_label"],
                "notes": "Explicit example labels detected via anchored patterns",
            },
        },
        {
            "rule_id": "A1_deny_explicit_examples_non_example_queries",
            "version": 1,
            "description": "Non-example queries deny explicitly labeled examples",
            "applies_when": {
                "query_intents": ["definition", "procedure", "constraint", "lookup"],
                "chunk_predicates": [
                    {
                        "field": "rhetoric_explicit.has_example_label",
                        "op": "is_true",
                        "value": None,
                    }
                ],
            },
            "decision": {"type": "DENY"},
            "provenance": {
                "derived_from": ["rhetoric_explicit.has_example_label"],
                "notes": "Explicit example labels detected via anchored patterns",
            },
        },
        {
            "rule_id": "A2_deny_explicit_variants_unless_allowed",
            "version": 1,
            "description": "Variant rules are inadmissible unless user asked for variants",
            "applies_when": {
                "query_intents": ["definition", "procedure", "constraint", "lookup"],
                "require_flags": {"allow_variants": False},
                "chunk_predicates": [
                    {
                        "field": "rhetoric_explicit.has_variant_label",
                        "op": "is_true",
                        "value": None,
                    }
                ],
            },
            "decision": {"type": "DENY"},
            "provenance": {
                "derived_from": [
                    "rhetoric_explicit.has_variant_label",
                    "layout.container_type",
                ],
                "notes": "Explicit variant labels or parser-marked variant containers",
            },
        },
        {
            "rule_id": "A3_allow_tables_lookup",
            "version": 1,
            "description": "Lookup queries allow tables/references",
            "applies_when": {
                "query_intents": ["lookup"],
                "chunk_predicates": [
                    {"field": "layout.block_type", "op": "eq", "value": "Table"}
                ],
            },
            "decision": {"type": "ALLOW"},
            "provenance": {
                "derived_from": ["layout.block_type"],
                "notes": "Parser-emitted block type",
            },
        },
    ]


def _build_conflict_rules() -> List[Dict[str, Any]]:
    """
    Build the static list of conflict resolution rules.

    These rules define pairwise comparisons between chunks.
    """
    return [
        {
            "rule_id": "C0_non_example_outranks_example",
            "version": 1,
            "description": "Core text outranks explicit examples",
            "applies_when": {
                "pair_predicates": [{"type": "one_is_example_other_not"}],
            },
            "decision": {"type": "A_OVER_B"},
            "provenance": {
                "derived_from": ["rhetoric_explicit.has_example_label"],
                "notes": "Non-example chunk outranks example chunk",
            },
        },
        {
            "rule_id": "C1_non_variant_outranks_variant_unless_allowed",
            "version": 1,
            "description": "Non-variant outranks variant (unless allow_variants true)",
            "applies_when": {
                "require_flags": {"allow_variants": False},
                "pair_predicates": [{"type": "one_is_variant_other_not"}],
            },
            "decision": {"type": "A_OVER_B"},
            "provenance": {
                "derived_from": [
                    "rhetoric_explicit.has_variant_label",
                    "layout.container_type",
                ],
                "notes": "Non-variant chunk outranks variant chunk",
            },
        },
        {
            "rule_id": "C3_resolved_unique_reference_outranks_local",
            "version": 1,
            "description": "Explicit deferral / reference outranks local text",
            "applies_when": {
                "pair_predicates": [{"type": "one_refs_other_resolved_unique"}],
            },
            "decision": {"type": "B_OVER_A"},
            "provenance": {
                "derived_from": ["references_explicit.explicit_section_refs"],
                "notes": "If A explicitly references B's section with resolved_unique, B outranks A",
            },
        },
    ]


def _build_constraint_sets() -> Dict[str, Any]:
    """
    Build the constraint sets for the CDS.

    Returns:
        {
            "admissibility_rules": [...],
            "conflict_rules": [...]
        }
    """
    return {
        "admissibility_rules": _build_admissibility_rules(),
        "conflict_rules": _build_conflict_rules(),
    }


# -------------------------
# Main CDS builders
# -------------------------


def build_cds_from_chunks(
    chunks: List[Dict[str, Any]], doc_id: str
) -> Dict[str, Any]:
    """
    Build a CDS document payload from enriched chunks.

    Args:
        chunks: List of enriched chunk dictionaries
        doc_id: Document identifier

    Returns:
        CDS document structure with outline, chunk_facts, and constraint_sets
    """
    # Build header ID -> text mapping for resolving section_hierarchy
    header_map = _build_header_id_mapping(chunks)

    # Build outline (uses resolved section paths)
    outline = _build_outline(chunks)

    # Collect section titles for reference resolution (using resolved paths)
    known_section_titles: Set[str] = set()
    for chunk in chunks:
        section_path = _get_resolved_section_path(chunk, header_map)
        for title in section_path:
            known_section_titles.add(title)

    # Build chunk facts with resolved section paths
    chunk_facts_list = []
    for ordinal, chunk in enumerate(chunks):
        # Get resolved section path
        resolved_path = _get_resolved_section_path(chunk, header_map)
        
        # Create a modified chunk dict with resolved section_path
        chunk_with_path = {**chunk, "section_path": resolved_path}
        
        facts = build_chunk_facts(chunk_with_path, ordinal, known_section_titles)
        chunk_facts_list.append(facts.to_dict())

    # Build constraint sets (static rules)
    constraint_sets = _build_constraint_sets()

    return {
        "document_id": doc_id,
        "outline": outline,
        "chunk_facts": chunk_facts_list,
        "constraint_sets": constraint_sets,
    }


def build_cds_for_run(merged_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build CDS for all documents in a run.

    Groups chunks by document_id and builds CDS for each.

    Args:
        merged_chunks: List of enriched chunks with document_id field

    Returns:
        CDS payload with schema_version and documents
    """
    # Group chunks by document
    docs: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in merged_chunks:
        doc_id = chunk.get("document_id", "unknown")
        if doc_id not in docs:
            docs[doc_id] = []
        docs[doc_id].append(chunk)

    # Build CDS for each document
    documents: Dict[str, Dict[str, Any]] = {}
    for doc_id, doc_chunks in docs.items():
        documents[doc_id] = build_cds_from_chunks(doc_chunks, doc_id)

    return {
        "schema_version": CDS_SCHEMA_VERSION,
        "documents": documents,
    }


def summarize_cds_for_graph(cds_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a compact summary of CDS for embedding in graph payload.

    Args:
        cds_payload: Full CDS payload

    Returns:
        Summary with document count, chunk count, and rule counts
    """
    documents = cds_payload.get("documents", {})

    total_chunks = 0
    total_chapters = 0
    total_sections = 0

    for doc in documents.values():
        total_chunks += len(doc.get("chunk_facts", []))
        outline = doc.get("outline", {})
        total_chapters += len(outline.get("chapters", []))
        total_sections += len(outline.get("sections", []))

    # Get rule counts from first document (all have same rules)
    admissibility_count = 0
    conflict_count = 0
    if documents:
        first_doc = next(iter(documents.values()))
        constraint_sets = first_doc.get("constraint_sets", {})
        admissibility_count = len(constraint_sets.get("admissibility_rules", []))
        conflict_count = len(constraint_sets.get("conflict_rules", []))

    all_chunk_facts: List[Dict[str, Any]] = []
    for doc in documents.values():
        all_chunk_facts.extend(doc.get("chunk_facts", []))
    als_metrics = compute_als_from_chunk_facts_dicts(all_chunk_facts)

    return {
        "schema_version": cds_payload.get("schema_version", CDS_SCHEMA_VERSION),
        "document_count": len(documents),
        "total_chunks": total_chunks,
        "total_chapters": total_chapters,
        "total_sections": total_sections,
        "admissibility_rules": admissibility_count,
        "conflict_rules": conflict_count,
        "authority_legibility": als_metrics,
    }


def load_cds_from_graph_payload(
    graph_payload: Dict[str, Any], base_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Load CDS from a file referenced in the graph payload.

    Args:
        graph_payload: Graph payload with potential "cds" field
        base_dir: Base directory to resolve relative paths

    Returns:
        CDS payload or None if not found
    """
    cds_info = graph_payload.get("cds", {})
    cds_path = cds_info.get("path")

    if not cds_path:
        return None

    cds_file = Path(cds_path)
    if not cds_file.is_absolute() and base_dir:
        cds_file = base_dir / cds_file

    if not cds_file.exists():
        return None

    with open(cds_file, "r", encoding="utf-8") as f:
        return json.load(f)


def build_cds_index(cds_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build a chunk_id -> chunk_facts index from CDS payload.

    Args:
        cds_payload: Full CDS payload

    Returns:
        Dictionary mapping chunk_id to chunk_facts dict
    """
    index: Dict[str, Dict[str, Any]] = {}

    for doc in cds_payload.get("documents", {}).values():
        for chunk_facts in doc.get("chunk_facts", []):
            chunk_id = chunk_facts.get("chunk_id")
            if chunk_id:
                index[chunk_id] = chunk_facts

    return index


# -------------------------
# Legacy API compatibility
# -------------------------

# These functions maintain backward compatibility with v0.1 API
# but now return v0.2 structures


def build_cds_from_chunks_legacy(
    chunks: List[Dict[str, Any]], doc_id: str
) -> Dict[str, Any]:
    """
    Legacy wrapper for build_cds_from_chunks.

    Deprecated: Use build_cds_from_chunks directly.
    """
    return build_cds_from_chunks(chunks, doc_id)
