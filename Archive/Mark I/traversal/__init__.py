"""
Traversal-only and hybrid retrieval system.

This package implements graph-based retrieval:
Query → Seeds → Traversal → Candidate Set

Hybrid retrieval adds:
Query → LLM Expansion → Parallel Search + Semantic Search → Rerank

Modules:
- config: TraversalConfig for ruleset-specific settings
- store: MongoDB storage for configs and index metadata
- index: TraversalIndex for fast anchor node lookup
- seeds: Query to anchor node mapping
- intent: Query intent classification
- policy: Traversal policies per intent
- traverse: Core BFS traversal function
- retriever: Complete traversal-only retrieval pipeline
- model_adapter: Provider-agnostic LLM interface (uses OpenAI Responses API)
- expander: LLM query expansion
- parallel_search: Parallel term search executor
- reranker: Score combination and reranking
- hybrid_retriever: Unified hybrid retrieval pipeline

Default model: gpt-5.2 (via OpenAI Responses API)
See: Docs/architecture/OpenAI_Responses_API.md
"""

from .config import TraversalConfig, build_config
from .index import TraversalIndex, tokenize_and_normalize
from .seeds import find_anchor_nodes, select_documents
from .intent import Intent, classify_intent, classify_intent_rules, classify_intent_llm
from .policy import TraversalPolicy, TraversalBudget, INTENT_POLICIES
from .traverse import traverse, traverse_with_ranks, traverse_with_diagnostics
from .retriever import retrieve_candidates, TraversalResult

# Hybrid retrieval components
from .model_adapter import (
    ModelAdapter,
    ModelProvider,
    ExpansionModelConfig,
    GenerationResult,
    EXPANSION_MODELS,
    DEFAULT_EXPANSION_MODEL,
    create_adapter,
    list_available_models,
    get_default_model,
    get_default_model_config,
)
from .expander import (
    ExpansionResult,
    QueryExpander,
    expand_query,
    expand_query_with_model,
)
from .parallel_search import (
    TermSearchResult,
    ParallelSearchResult,
    search_term,
    search_terms_parallel,
    execute_parallel_search,
    get_top_k_chunks,
)
from .reranker import (
    RerankStrategy,
    RerankConfig,
    RankedChunk,
    RerankResult,
    rerank,
    get_top_k,
    analyze_attribution,
)
from .hybrid_retriever import (
    HybridConfig,
    RetrievalDiagnostics,
    HybridRetrievalResult,
    HybridRetriever,
    create_hybrid_retriever,
)

# MongoDB storage (lazy import to avoid requiring pymongo)
def get_store():
    """Lazy import of store module."""
    from . import store
    return store

__all__ = [
    # Config
    "TraversalConfig",
    "build_config",
    # Index
    "TraversalIndex",
    "tokenize_and_normalize",
    # Seeds
    "find_anchor_nodes",
    "select_documents",
    # Intent
    "Intent",
    "classify_intent",
    "classify_intent_rules",
    "classify_intent_llm",
    # Policy
    "TraversalPolicy",
    "TraversalBudget",
    "INTENT_POLICIES",
    # Traverse
    "traverse",
    "traverse_with_ranks",
    "traverse_with_diagnostics",
    # Retriever (traversal-only)
    "retrieve_candidates",
    "TraversalResult",
    # Model adapter
    "ModelAdapter",
    "ModelProvider",
    "ExpansionModelConfig",
    "GenerationResult",
    "EXPANSION_MODELS",
    "DEFAULT_EXPANSION_MODEL",
    "create_adapter",
    "list_available_models",
    "get_default_model",
    "get_default_model_config",
    # Expander
    "ExpansionResult",
    "QueryExpander",
    "expand_query",
    "expand_query_with_model",
    # Parallel search
    "TermSearchResult",
    "ParallelSearchResult",
    "search_term",
    "search_terms_parallel",
    "execute_parallel_search",
    "get_top_k_chunks",
    # Reranker
    "RerankStrategy",
    "RerankConfig",
    "RankedChunk",
    "RerankResult",
    "rerank",
    "get_top_k",
    "analyze_attribution",
    # Hybrid retriever
    "HybridConfig",
    "RetrievalDiagnostics",
    "HybridRetrievalResult",
    "HybridRetriever",
    "create_hybrid_retriever",
    # Store
    "get_store",
]
