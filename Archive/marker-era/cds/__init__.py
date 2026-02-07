"""
CDS (Canonical Document Skeleton) Module v0.2

Provides:
- ChunkFacts: Observed facts about chunks (no semantic inference)
- Constraint Engine: Late-only admissibility and conflict resolution
- CDS Builder: Document skeleton with outline, facts, and constraints
- T3 Harness: Non-regression test for admissibility filtering
"""

# CDS Builder (v0.2 structure)
from .cds_builder import (
    CDS_SCHEMA_VERSION,
    build_cds_from_chunks,
    build_cds_for_run,
    build_cds_index,
    load_cds_from_graph_payload,
    summarize_cds_for_graph,
)

# Constraint Engine
from .constraint_engine import (
    # Enums
    QueryIntent,
    AdmissibilityDecision,
    ConflictDecision,
    LayoutTier,
    SectionRole,
    ContentKind,
    # Data classes
    QueryContext,
    ChunkFacts,
    T3Result,
    # Query classification
    derive_query_context,
    # Engine
    ConstraintEngine,
    authority_key,
    build_minimal_engine,
    # T3 Harness
    enforce_t3_for_query,
    enforce_t3_suite,
    # Rule classes (for extension)
    AdmissibilityRule,
    ConflictRule,
    AllowExplicitExamplesForExampleRequests,
    DenyExplicitExamplesForNonExampleQueries,
    DenyExplicitVariantsUnlessAllowed,
    AllowTablesForLookup,
    DenyLayoutTierExampleVariantForNonExampleQueries,
    NonExampleOutranksExample,
    NonVariantOutranksVariantUnlessAllowed,
    ResolvedUniqueReferenceOutranksLocal,
)

# ChunkFacts Adapter
from .chunk_facts_adapter import (
    build_chunk_facts,
    build_chunk_facts_index,
    chunks_to_chunk_facts_list,
)

__all__ = [
    # Schema version
    "CDS_SCHEMA_VERSION",
    # CDS Builder
    "build_cds_from_chunks",
    "build_cds_for_run",
    "build_cds_index",
    "load_cds_from_graph_payload",
    "summarize_cds_for_graph",
    # Enums
    "QueryIntent",
    "AdmissibilityDecision",
    "ConflictDecision",
    "LayoutTier",
    "SectionRole",
    "ContentKind",
    # Data classes
    "QueryContext",
    "ChunkFacts",
    "T3Result",
    "authority_key",
    # Query classification
    "derive_query_context",
    # Engine
    "ConstraintEngine",
    "build_minimal_engine",
    # T3 Harness
    "enforce_t3_for_query",
    "enforce_t3_suite",
    # ChunkFacts Adapter
    "build_chunk_facts",
    "build_chunk_facts_index",
    "chunks_to_chunk_facts_list",
    # Rule base classes
    "AdmissibilityRule",
    "ConflictRule",
    # Built-in rules
    "AllowExplicitExamplesForExampleRequests",
    "DenyExplicitExamplesForNonExampleQueries",
    "DenyExplicitVariantsUnlessAllowed",
    "AllowTablesForLookup",
    "DenyLayoutTierExampleVariantForNonExampleQueries",
    "NonExampleOutranksExample",
    "NonVariantOutranksVariantUnlessAllowed",
    "ResolvedUniqueReferenceOutranksLocal",
]
