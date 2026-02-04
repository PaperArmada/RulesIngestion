"""
Unified hybrid retrieval pipeline.

Orchestrates the complete hybrid retrieval flow:
1. Intent classification
2. LLM query expansion (parallel terms)
3. Parallel deterministic search
4. Parallel semantic search (if embeddings available)
5. Reranking with configurable weights
6. Result synthesis with diagnostics

Provides RetrievalDiagnostics for observability and tuning.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .index import TraversalIndex, tokenize_and_normalize
from .intent import Intent, classify_intent
from .expander import (
    ExpansionResult,
    QueryExpander,
    expand_query,
)
from .model_adapter import (
    ModelAdapter,
    ExpansionModelConfig,
    create_adapter,
    EXPANSION_MODELS,
    DEFAULT_EXPANSION_MODEL,
)
from .parallel_search import (
    ParallelSearchResult,
    execute_parallel_search,
    get_top_k_chunks,
)
from .reranker import (
    RerankConfig,
    RerankResult,
    RerankStrategy,
    RankedChunk,
    rerank,
    get_top_k,
    analyze_attribution,
)
from .policy import get_policy
from .traverse import traverse_with_ranks


@dataclass
class HybridConfig:
    """
    Configuration for hybrid retrieval.
    
    Attributes:
        expansion_model: Model name or config for query expansion
        expansion_terms: Number of expansion terms to generate
        deterministic_weight: Weight for deterministic path (0-1)
        semantic_weight: Weight for semantic path (0-1)
        anchor_bonus: Score bonus for anchor chunks
        term_coverage_bonus: Score bonus per matched expansion term
        anchor_term_bonus: Score bonus per matched anchor term (higher priority)
        anchor_term_multiplier: IDF multiplier for anchor terms (from original query)
        max_term_match_threshold: Threshold above which diminishing returns penalty applies
        top_k: Number of results to return
        enable_semantic: Whether to use semantic search (requires embeddings)
        semantic_search_fn: Optional custom semantic search function
        require_both_paths: Only include chunks found by both paths
        use_idf: Use IDF weighting for term scoring (rare terms score higher)
        fusion_strategy: How to combine scores ("weighted_sum" or "rrf")
        enable_traversal: Whether to include traversal in RRF fusion
        rrf_k: Smoothing constant for RRF (default 60)
    """
    expansion_model: Union[str, ExpansionModelConfig] = None  # Uses DEFAULT_EXPANSION_MODEL
    expansion_terms: int = 7
    deterministic_weight: float = 0.5
    semantic_weight: float = 0.5
    anchor_bonus: float = 1.0
    term_coverage_bonus: float = 0.1
    anchor_term_bonus: float = 0.3  # Higher bonus for anchor term matches
    anchor_term_multiplier: float = 2.0  # IDF multiplier for anchor terms
    max_term_match_threshold: int = 6  # Diminishing returns threshold
    top_k: int = 30
    enable_semantic: bool = True
    semantic_search_fn: Optional[Callable[[str, int], List[Dict]]] = None
    require_both_paths: bool = False
    use_idf: bool = True  # Default to True for improved scoring
    fusion_strategy: str = "weighted_sum"  # "weighted_sum" or "rrf"
    enable_traversal: bool = False  # Include traversal in RRF fusion
    rrf_k: int = 60  # RRF smoothing constant
    
    def with_weights(
        self,
        deterministic: float,
        semantic: float,
    ) -> "HybridConfig":
        """Create a copy with different weights."""
        return HybridConfig(
            expansion_model=self.expansion_model,
            expansion_terms=self.expansion_terms,
            deterministic_weight=deterministic,
            semantic_weight=semantic,
            anchor_bonus=self.anchor_bonus,
            term_coverage_bonus=self.term_coverage_bonus,
            anchor_term_bonus=self.anchor_term_bonus,
            anchor_term_multiplier=self.anchor_term_multiplier,
            max_term_match_threshold=self.max_term_match_threshold,
            top_k=self.top_k,
            enable_semantic=self.enable_semantic,
            semantic_search_fn=self.semantic_search_fn,
            require_both_paths=self.require_both_paths,
            use_idf=self.use_idf,
            fusion_strategy=self.fusion_strategy,
            enable_traversal=self.enable_traversal,
            rrf_k=self.rrf_k,
        )
    
    def with_rrf(
        self,
        enable_traversal: bool = True,
        rrf_k: int = 60,
    ) -> "HybridConfig":
        """Create a copy with RRF fusion strategy."""
        return HybridConfig(
            expansion_model=self.expansion_model,
            expansion_terms=self.expansion_terms,
            deterministic_weight=self.deterministic_weight,
            semantic_weight=self.semantic_weight,
            anchor_bonus=self.anchor_bonus,
            term_coverage_bonus=self.term_coverage_bonus,
            anchor_term_bonus=self.anchor_term_bonus,
            anchor_term_multiplier=self.anchor_term_multiplier,
            max_term_match_threshold=self.max_term_match_threshold,
            top_k=self.top_k,
            enable_semantic=self.enable_semantic,
            semantic_search_fn=self.semantic_search_fn,
            require_both_paths=self.require_both_paths,
            use_idf=self.use_idf,
            fusion_strategy="rrf",
            enable_traversal=enable_traversal,
            rrf_k=rrf_k,
        )
    
    def with_model(self, model_name: str) -> "HybridConfig":
        """Create a copy with a different expansion model."""
        return HybridConfig(
            expansion_model=model_name,
            expansion_terms=self.expansion_terms,
            deterministic_weight=self.deterministic_weight,
            semantic_weight=self.semantic_weight,
            anchor_bonus=self.anchor_bonus,
            term_coverage_bonus=self.term_coverage_bonus,
            anchor_term_bonus=self.anchor_term_bonus,
            anchor_term_multiplier=self.anchor_term_multiplier,
            max_term_match_threshold=self.max_term_match_threshold,
            top_k=self.top_k,
            enable_semantic=self.enable_semantic,
            semantic_search_fn=self.semantic_search_fn,
            require_both_paths=self.require_both_paths,
            use_idf=self.use_idf,
            fusion_strategy=self.fusion_strategy,
            enable_traversal=self.enable_traversal,
            rrf_k=self.rrf_k,
        )
    
    def with_idf(self, use_idf: bool) -> "HybridConfig":
        """Create a copy with different IDF setting."""
        return HybridConfig(
            expansion_model=self.expansion_model,
            expansion_terms=self.expansion_terms,
            deterministic_weight=self.deterministic_weight,
            semantic_weight=self.semantic_weight,
            anchor_bonus=self.anchor_bonus,
            term_coverage_bonus=self.term_coverage_bonus,
            anchor_term_bonus=self.anchor_term_bonus,
            anchor_term_multiplier=self.anchor_term_multiplier,
            max_term_match_threshold=self.max_term_match_threshold,
            top_k=self.top_k,
            enable_semantic=self.enable_semantic,
            semantic_search_fn=self.semantic_search_fn,
            require_both_paths=self.require_both_paths,
            use_idf=use_idf,
            fusion_strategy=self.fusion_strategy,
            enable_traversal=self.enable_traversal,
            rrf_k=self.rrf_k,
        )


@dataclass
class RetrievalDiagnostics:
    """
    Comprehensive diagnostics for a single retrieval.
    
    Used for observability, debugging, and tuning experiments.
    """
    # Query info
    query: str
    intent: Intent
    
    # Expansion info
    anchor_terms: List[str]  # Terms from original query (priority weighting)
    expanded_terms: List[str]  # LLM-generated expansion terms
    expansion_latency_ms: float
    expansion_tokens: int
    expansion_model: str
    
    # Deterministic path
    deterministic_chunks_found: int
    deterministic_latency_ms: float
    terms_with_hits: int
    term_hit_rate: float
    
    # IDF scoring info
    use_idf: bool = True
    total_idf_score: float = 0.0
    avg_idf_per_term: float = 0.0
    bigram_matches: int = 0
    
    # Semantic path (if enabled)
    semantic_chunks_found: int = 0
    semantic_latency_ms: float = 0.0
    semantic_enabled: bool = False
    
    # Traversal path (for 3-way RRF)
    traversal_chunks_found: int = 0
    traversal_latency_ms: float = 0.0
    traversal_enabled: bool = False
    
    # Fusion strategy info
    fusion_strategy: str = "weighted_sum"
    
    # Combined results
    overlap_count: int = 0
    final_result_count: int = 0
    rerank_latency_ms: float = 0.0
    
    # Total timing
    total_latency_ms: float = 0.0
    
    # Gold chunk analysis (if gold_chunk_ids provided)
    gold_analysis: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "query": self.query,
            "intent": self.intent.name,
            "anchor_terms": self.anchor_terms,
            "expanded_terms": self.expanded_terms,
            "expansion_latency_ms": self.expansion_latency_ms,
            "expansion_tokens": self.expansion_tokens,
            "expansion_model": self.expansion_model,
            "deterministic_chunks_found": self.deterministic_chunks_found,
            "deterministic_latency_ms": self.deterministic_latency_ms,
            "terms_with_hits": self.terms_with_hits,
            "term_hit_rate": self.term_hit_rate,
            "use_idf": self.use_idf,
            "total_idf_score": self.total_idf_score,
            "avg_idf_per_term": self.avg_idf_per_term,
            "bigram_matches": self.bigram_matches,
            "semantic_chunks_found": self.semantic_chunks_found,
            "semantic_latency_ms": self.semantic_latency_ms,
            "semantic_enabled": self.semantic_enabled,
            "traversal_chunks_found": self.traversal_chunks_found,
            "traversal_latency_ms": self.traversal_latency_ms,
            "traversal_enabled": self.traversal_enabled,
            "fusion_strategy": self.fusion_strategy,
            "overlap_count": self.overlap_count,
            "final_result_count": self.final_result_count,
            "rerank_latency_ms": self.rerank_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "gold_analysis": self.gold_analysis,
        }


@dataclass
class HybridRetrievalResult:
    """
    Complete result from hybrid retrieval.
    
    Attributes:
        ranked_chunks: Final ranked list of chunks
        diagnostics: Detailed diagnostics for observability
        expansion_result: Raw expansion result
        parallel_search_result: Raw parallel search result
        rerank_result: Raw rerank result
    """
    ranked_chunks: List[RankedChunk]
    diagnostics: RetrievalDiagnostics
    expansion_result: Optional[ExpansionResult] = None
    parallel_search_result: Optional[ParallelSearchResult] = None
    rerank_result: Optional[RerankResult] = None
    
    def get_top_k(self, k: int) -> List[RankedChunk]:
        """Get top-k ranked chunks."""
        return self.ranked_chunks[:k]
    
    def get_chunk_ids(self, k: Optional[int] = None) -> List[str]:
        """Get chunk IDs from top-k results."""
        chunks = self.ranked_chunks[:k] if k else self.ranked_chunks
        return [c.chunk_id for c in chunks]
    
    def contains_any_gold(self, gold_chunk_ids: Set[str], k: int = 30) -> bool:
        """Check if any gold chunk appears in top-k."""
        top_k_ids = set(self.get_chunk_ids(k))
        return bool(top_k_ids & gold_chunk_ids)


class HybridRetriever:
    """
    Main hybrid retrieval orchestrator.
    
    Usage:
        retriever = HybridRetriever(index, config)
        result = retriever.retrieve("What does flat-footed do?")
        
        # With gold chunks for evaluation
        result = retriever.retrieve(
            "What does flat-footed do?",
            gold_chunk_ids={"chunk-123", "chunk-456"}
        )
    """
    
    def __init__(
        self,
        index: TraversalIndex,
        config: Optional[HybridConfig] = None,
    ):
        """
        Initialize the hybrid retriever.
        
        Args:
            index: TraversalIndex with pre-built indexes
            config: HybridConfig (uses defaults if not provided)
        """
        self.index = index
        self.config = config or HybridConfig()
        self._expander: Optional[QueryExpander] = None
        
        # Metrics tracking
        self._retrieval_count = 0
        self._total_latency_ms = 0.0
    
    @property
    def expander(self) -> QueryExpander:
        """Get or create the query expander."""
        if self._expander is None:
            self._expander = QueryExpander(self.config.expansion_model)
        return self._expander
    
    def retrieve(
        self,
        query: str,
        gold_chunk_ids: Optional[Set[str]] = None,
        intent: Optional[Intent] = None,
    ) -> HybridRetrievalResult:
        """
        Execute hybrid retrieval for a query.
        
        Supports multiple fusion strategies:
        - weighted_sum: Traditional weighted combination of scores
        - rrf: Reciprocal Rank Fusion (2-way or 3-way with traversal)
        
        Args:
            query: The user query
            gold_chunk_ids: Optional set of expected chunk IDs (for evaluation)
            intent: Optional pre-classified intent
            
        Returns:
            HybridRetrievalResult with ranked chunks and diagnostics
        """
        start_time = time.perf_counter()
        
        # 1. Classify intent
        if intent is None:
            intent = classify_intent(query)
        
        # 2. Traversal (fast! ~1ms) - run first to get depth-based ranks
        traversal_ranks: Dict[str, int] = {}
        trav_latency = 0.0
        
        if self.config.enable_traversal or self.config.fusion_strategy == "rrf":
            trav_start = time.perf_counter()
            try:
                from .seeds import find_anchor_nodes
                anchors = find_anchor_nodes(query, self.index)
                if anchors:
                    policy = get_policy(intent)
                    trav_result = traverse_with_ranks(
                        self.index,
                        anchors,
                        policy,
                    )
                    traversal_ranks = trav_result.get("chunk_ranks", {})
            except Exception as e:
                print(f"⚠️ [HybridRetriever] Traversal failed: {e}")
            trav_latency = (time.perf_counter() - trav_start) * 1000
        
        # 3. Expand query
        expansion_start = time.perf_counter()
        expansion_result = self.expander.expand(query, intent)
        expansion_latency = (time.perf_counter() - expansion_start) * 1000
        
        expanded_terms = expansion_result.expanded_terms
        
        # 4. Parallel deterministic search
        det_start = time.perf_counter()
        parallel_result = execute_parallel_search(
            terms=expanded_terms,
            index=self.index,
            original_query=query,
            anchor_bonus=self.config.anchor_bonus,
            anchor_terms=expansion_result.anchor_terms,
            anchor_term_multiplier=self.config.anchor_term_multiplier,
            max_term_match_threshold=self.config.max_term_match_threshold,
            use_idf=self.config.use_idf,
        )
        det_latency = (time.perf_counter() - det_start) * 1000
        
        # Get deterministic results
        det_results = get_top_k_chunks(
            parallel_result,
            self.index,
            k=self.config.top_k * 2,  # Get more for reranking
        )
        
        # 5. Semantic search (if enabled)
        sem_results: List[Dict[str, Any]] = []
        sem_latency = 0.0
        
        if self.config.enable_semantic and self.config.semantic_search_fn:
            sem_start = time.perf_counter()
            try:
                sem_results = self.config.semantic_search_fn(
                    query,
                    self.config.top_k * 2,
                )
            except Exception as e:
                # Log but continue without semantic
                print(f"⚠️ [HybridRetriever] Semantic search failed: {e}")
                sem_results = []
            sem_latency = (time.perf_counter() - sem_start) * 1000
        
        # 6. Rerank with chosen strategy
        rerank_start = time.perf_counter()
        
        # Select strategy
        strategy = RerankStrategy.WEIGHTED_SUM
        if self.config.fusion_strategy == "rrf":
            strategy = RerankStrategy.RECIPROCAL_RANK
        
        rerank_config = RerankConfig(
            deterministic_weight=self.config.deterministic_weight,
            semantic_weight=self.config.semantic_weight,
            strategy=strategy,
            anchor_bonus=self.config.anchor_bonus,
            term_coverage_bonus=self.config.term_coverage_bonus,
            anchor_term_bonus=self.config.anchor_term_bonus,
            require_both=self.config.require_both_paths,
            rrf_k=self.config.rrf_k,
        )
        
        # Find anchor chunks
        anchor_ids = set()
        query_terms = set(tokenize_and_normalize(query))
        for det_result in det_results:
            if det_result.get("terms_matched", 0) >= len(query_terms):
                anchor_ids.add(det_result["chunk_id"])
        
        # Pass traversal ranks for 3-way RRF
        trav_ranks_for_rerank = traversal_ranks if self.config.enable_traversal else None
        
        rerank_result = rerank(
            deterministic_results=det_results,
            semantic_results=sem_results,
            config=rerank_config,
            anchor_chunk_ids=anchor_ids,
            anchor_terms=expansion_result.anchor_terms,
            traversal_ranks=trav_ranks_for_rerank,
        )
        
        rerank_latency = (time.perf_counter() - rerank_start) * 1000
        
        # Get final ranked chunks
        ranked_chunks = get_top_k(rerank_result, self.config.top_k)
        
        total_latency = (time.perf_counter() - start_time) * 1000
        
        # 7. Build diagnostics
        gold_analysis = None
        if gold_chunk_ids:
            gold_analysis = analyze_attribution(rerank_result, gold_chunk_ids)
        
        diagnostics = RetrievalDiagnostics(
            query=query,
            intent=intent,
            anchor_terms=expansion_result.anchor_terms,
            expanded_terms=expanded_terms,
            expansion_latency_ms=expansion_latency,
            expansion_tokens=expansion_result.generation_result.total_tokens if expansion_result.generation_result else 0,
            expansion_model=self.expander.adapter.config.model_id,
            deterministic_chunks_found=len(parallel_result.combined_chunks),
            deterministic_latency_ms=det_latency,
            terms_with_hits=parallel_result.search_stats.get("terms_with_hits", 0),
            term_hit_rate=parallel_result.search_stats.get("term_hit_rate", 0.0),
            use_idf=self.config.use_idf,
            total_idf_score=parallel_result.search_stats.get("total_idf_score", 0.0),
            avg_idf_per_term=parallel_result.search_stats.get("avg_idf_per_term", 0.0),
            bigram_matches=parallel_result.search_stats.get("bigram_matches", 0),
            semantic_chunks_found=len(sem_results),
            semantic_latency_ms=sem_latency,
            semantic_enabled=self.config.enable_semantic and self.config.semantic_search_fn is not None,
            traversal_chunks_found=len(traversal_ranks),
            traversal_latency_ms=trav_latency,
            traversal_enabled=self.config.enable_traversal,
            fusion_strategy=self.config.fusion_strategy,
            overlap_count=rerank_result.overlap_count,
            final_result_count=len(ranked_chunks),
            rerank_latency_ms=rerank_latency,
            total_latency_ms=total_latency,
            gold_analysis=gold_analysis,
        )
        
        # Update metrics
        self._retrieval_count += 1
        self._total_latency_ms += total_latency
        
        return HybridRetrievalResult(
            ranked_chunks=ranked_chunks,
            diagnostics=diagnostics,
            expansion_result=expansion_result,
            parallel_search_result=parallel_result,
            rerank_result=rerank_result,
        )
    
    def retrieve_batch(
        self,
        queries: List[str],
        gold_chunk_ids_list: Optional[List[Set[str]]] = None,
    ) -> List[HybridRetrievalResult]:
        """
        Retrieve for multiple queries.
        
        Args:
            queries: List of query strings
            gold_chunk_ids_list: Optional list of gold chunk ID sets
            
        Returns:
            List of HybridRetrievalResult
        """
        results = []
        gold_list = gold_chunk_ids_list or [None] * len(queries)
        
        for query, gold_ids in zip(queries, gold_list):
            result = self.retrieve(query, gold_chunk_ids=gold_ids)
            results.append(result)
        
        return results
    
    def compute_recall_at_k(
        self,
        result: HybridRetrievalResult,
        gold_chunk_ids: Set[str],
        k_values: List[int] = [1, 2, 5, 10, 20, 30],
    ) -> Dict[int, float]:
        """
        Compute Recall@K for a retrieval result.
        
        Recall@K = fraction of gold chunks that appear in top-K results.
        
        Args:
            result: HybridRetrievalResult
            gold_chunk_ids: Set of expected correct chunk IDs
            k_values: K values to compute recall at
            
        Returns:
            Dict mapping k to recall value
        """
        recall_at_k = {}
        
        for k in k_values:
            top_k_ids = set(result.get_chunk_ids(k))
            hits = len(top_k_ids & gold_chunk_ids)
            recall = hits / max(1, len(gold_chunk_ids))
            recall_at_k[k] = recall
        
        return recall_at_k
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics."""
        return {
            "retrieval_count": self._retrieval_count,
            "total_latency_ms": self._total_latency_ms,
            "avg_latency_ms": self._total_latency_ms / max(1, self._retrieval_count),
            "expander_metrics": self.expander.metrics if self._expander else {},
        }
    
    def reset_metrics(self) -> None:
        """Reset accumulated metrics."""
        self._retrieval_count = 0
        self._total_latency_ms = 0.0
        if self._expander:
            self._expander.reset_metrics()
    
    def with_config(self, config: HybridConfig) -> "HybridRetriever":
        """Create a new retriever with different config."""
        return HybridRetriever(self.index, config)


def create_hybrid_retriever(
    index: TraversalIndex,
    expansion_model: str = None,  # Uses DEFAULT_EXPANSION_MODEL (gpt-5.2)
    deterministic_weight: float = 0.5,
    semantic_weight: float = 0.5,
    semantic_search_fn: Optional[Callable[[str, int], List[Dict]]] = None,
) -> HybridRetriever:
    """
    Factory function to create a hybrid retriever.
    
    Args:
        index: TraversalIndex
        expansion_model: Model name for query expansion (defaults to DEFAULT_EXPANSION_MODEL)
        deterministic_weight: Weight for deterministic path
        semantic_weight: Weight for semantic path
        semantic_search_fn: Optional semantic search function
        
    Returns:
        Configured HybridRetriever
    """
    # Resolve default model
    effective_model = expansion_model if expansion_model is not None else DEFAULT_EXPANSION_MODEL
    
    config = HybridConfig(
        expansion_model=effective_model,
        deterministic_weight=deterministic_weight,
        semantic_weight=semantic_weight,
        semantic_search_fn=semantic_search_fn,
        enable_semantic=semantic_search_fn is not None,
    )
    
    return HybridRetriever(index, config)
