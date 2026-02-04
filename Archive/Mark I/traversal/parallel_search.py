"""
Parallel search executor for hybrid retrieval.

Executes multiple search terms concurrently against the TraversalIndex,
combining results with configurable scoring.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .index import TraversalIndex, tokenize_and_normalize

# Bonus multiplier for bigram (phrase) matches
BIGRAM_BONUS: float = 2.0

# Bonus multiplier for exact phrase matches (full term as phrase)
EXACT_PHRASE_BONUS: float = 3.0


@dataclass
class TermSearchResult:
    """
    Result from searching a single term.
    
    Attributes:
        term: The search term
        chunk_ids: Set of matching chunk IDs
        search_type: How the match was found (term, section, entity, tag, trait, bigram, exact_phrase)
        hit_count: Number of chunks matched
        latency_ms: Time taken to search this term
        idf_score: Sum of IDF weights for matched tokens (rare terms score higher)
        matched_tokens: List of tokens that matched
        matched_bigrams: List of bigrams that matched (for phrase matching)
        matched_phrases: List of exact phrases that matched (full multi-word terms)
    """
    term: str
    chunk_ids: Set[str]
    search_type: str
    hit_count: int
    latency_ms: float = 0.0
    idf_score: float = 1.0  # Default to 1.0 for backward compatibility
    matched_tokens: List[str] = field(default_factory=list)
    matched_bigrams: List[str] = field(default_factory=list)
    matched_phrases: List[str] = field(default_factory=list)  # Exact phrase matches


@dataclass
class ParallelSearchResult:
    """
    Combined result from parallel term searches.
    
    Attributes:
        query_terms: The expanded search terms used
        term_results: Individual results per term
        combined_chunks: All unique chunks found
        chunk_scores: Chunk ID → score based on term coverage
        total_latency_ms: Total execution time
        search_stats: Statistics about the search
    """
    query_terms: List[str]
    term_results: List[TermSearchResult]
    combined_chunks: Set[str]
    chunk_scores: Dict[str, float]
    total_latency_ms: float
    search_stats: Dict[str, Any] = field(default_factory=dict)


def search_term(
    term: str,
    index: TraversalIndex,
) -> TermSearchResult:
    """
    Search for a single term across all indexes.
    
    Searches in priority order:
    0. Exact phrase match (full multi-word term joined as phrase - highest specificity)
    1. Bigram matches (for multi-word terms - high specificity)
    2. Exact term match in term_to_chunks
    3. Section title match
    4. Entity name match
    5. Tag match
    6. Trait match
    7. Content kind match
    
    Returns combined results with IDF-weighted score.
    Rare terms contribute more to the score than common terms.
    """
    start = time.perf_counter()
    
    term_lower = term.lower().strip()
    chunk_ids: Set[str] = set()
    search_type = "none"
    matched_tokens: List[str] = []
    matched_bigrams: List[str] = []
    matched_phrases: List[str] = []
    idf_score: float = 0.0
    
    # Tokenize multi-word terms
    tokens = tokenize_and_normalize(term)
    
    # 0. Try exact phrase match first (highest priority for multi-word terms)
    # Check if the full term joined as underscore exists in bigram index
    if len(tokens) >= 2:
        # Try full phrase as a single key
        phrase_key = "_".join(tokens)
        if phrase_key in index.bigram_to_chunks:
            chunk_ids |= index.bigram_to_chunks[phrase_key]
            matched_phrases.append(phrase_key)
            # Full phrase match gets highest bonus
            phrase_idf = index.bigram_idf.get(phrase_key, 1.0)
            idf_score += phrase_idf * EXACT_PHRASE_BONUS
            search_type = "exact_phrase"
    
    # 1. Try bigram matches (for multi-word terms)
    # Bigrams are more specific than individual tokens
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}_{tokens[i+1]}"
            if bigram in index.bigram_to_chunks:
                chunk_ids |= index.bigram_to_chunks[bigram]
                matched_bigrams.append(bigram)
                # Bigram IDF with bonus for phrase match
                bigram_idf = index.bigram_idf.get(bigram, 1.0)
                idf_score += bigram_idf * BIGRAM_BONUS
                if search_type == "none":
                    search_type = "bigram"
    
    # 1. Try exact term match first
    for token in tokens:
        if token in index.term_to_chunks:
            chunk_ids |= index.term_to_chunks[token]
            matched_tokens.append(token)
            # Add IDF score for this token
            idf_score += index.term_idf.get(token, 1.0)
            if search_type == "none":
                search_type = "term"
    
    # Also try the full term as-is (for phrases)
    if term_lower in index.term_to_chunks:
        chunk_ids |= index.term_to_chunks[term_lower]
        if term_lower not in matched_tokens:
            matched_tokens.append(term_lower)
            idf_score += index.term_idf.get(term_lower, 1.0)
        if search_type == "none":
            search_type = "term"
    
    # 2. Section title match
    if term_lower in index.section_title_to_chunks:
        chunk_ids |= index.section_title_to_chunks[term_lower]
        if search_type == "none":
            search_type = "section"
    for token in tokens:
        if token in index.section_title_to_chunks:
            chunk_ids |= index.section_title_to_chunks[token]
            # Only add IDF if not already counted from term match
            if token not in matched_tokens:
                matched_tokens.append(token)
                idf_score += index.term_idf.get(token, 1.0)
            if search_type == "none":
                search_type = "section"
    
    # 3. Entity name match
    if term_lower in index.entity_name_to_id:
        entity_id = index.entity_name_to_id[term_lower]
        if entity_id in index.entity_to_chunks:
            chunk_ids |= index.entity_to_chunks[entity_id]
            if search_type == "none":
                search_type = "entity"
    
    # 4. Tag match
    if term_lower in index.tag_to_chunks:
        chunk_ids |= index.tag_to_chunks[term_lower]
        if search_type == "none":
            search_type = "tag"
    for token in tokens:
        if token in index.tag_to_chunks:
            chunk_ids |= index.tag_to_chunks[token]
            if search_type == "none":
                search_type = "tag"
    
    # 5. Trait match
    if term_lower in index.trait_to_chunks:
        chunk_ids |= index.trait_to_chunks[term_lower]
        if search_type == "none":
            search_type = "trait"
    for token in tokens:
        if token in index.trait_to_chunks:
            chunk_ids |= index.trait_to_chunks[token]
            if search_type == "none":
                search_type = "trait"
    
    # 6. Content kind match (for terms like "spell", "feat")
    content_kinds = {"spell", "feat", "item", "condition", "action", "rule", "trait"}
    for token in tokens:
        if token in content_kinds and token in index.content_kind_to_chunks:
            chunk_ids |= index.content_kind_to_chunks[token]
            if search_type == "none":
                search_type = "content_kind"
    
    # Default IDF to 1.0 if no tokens matched (backward compatibility)
    if idf_score == 0.0:
        idf_score = 1.0
    
    latency_ms = (time.perf_counter() - start) * 1000
    
    return TermSearchResult(
        term=term,
        chunk_ids=chunk_ids,
        search_type=search_type,
        hit_count=len(chunk_ids),
        latency_ms=latency_ms,
        idf_score=idf_score,
        matched_tokens=matched_tokens,
        matched_bigrams=matched_bigrams,
        matched_phrases=matched_phrases,
    )


def search_terms_parallel(
    terms: List[str],
    index: TraversalIndex,
    max_workers: int = 5,
) -> List[TermSearchResult]:
    """
    Search multiple terms in parallel.
    
    Args:
        terms: List of search terms
        index: TraversalIndex to search
        max_workers: Maximum parallel threads
        
    Returns:
        List of TermSearchResult, one per term
    """
    # For small term counts, just run sequentially (thread overhead isn't worth it)
    if len(terms) <= 3:
        return [search_term(t, index) for t in terms]
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(search_term, t, index): t for t in terms}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    
    # Maintain original order
    term_to_result = {r.term: r for r in results}
    return [term_to_result.get(t, search_term(t, index)) for t in terms]


def compute_chunk_scores(
    term_results: List[TermSearchResult],
    index: TraversalIndex,
    anchor_bonus: float = 2.0,
    anchor_chunk_ids: Optional[Set[str]] = None,
    anchor_terms: Optional[List[str]] = None,
    anchor_term_multiplier: float = 2.0,
    max_term_match_threshold: int = 6,
    use_idf: bool = True,
) -> Dict[str, float]:
    """
    Compute scores for chunks based on term coverage with IDF weighting.
    
    Scoring with IDF (use_idf=True):
    - For each chunk, compute IDF based on which query tokens actually appear
    - Rare tokens (high IDF) contribute more than common tokens (low IDF)
    - Exact phrase matches get highest bonus (EXACT_PHRASE_BONUS = 3.0x)
    - Bigram matches include a bonus for phrase specificity (BIGRAM_BONUS = 2.0x)
    - Anchor terms (from original query) get priority weighting (anchor_term_multiplier)
    - Anchors (chunks matching original query) get a bonus
    - Chunks matching many terms (>threshold) get diminishing returns penalty
    
    Scoring without IDF (use_idf=False - legacy mode):
    - Each term hit adds 1.0 to the chunk's score
    - All terms weighted equally
    
    Args:
        term_results: Results from term searches
        index: TraversalIndex with IDF values
        anchor_bonus: Extra score for anchor chunks
        anchor_chunk_ids: Set of anchor chunk IDs (from original query)
        anchor_terms: List of anchor terms from original query (priority weighting)
        anchor_term_multiplier: Multiplier for anchor term IDF (default 2.0)
        max_term_match_threshold: Threshold above which diminishing returns applies (default 6)
        use_idf: Whether to use IDF weighting (default True)
        
    Returns:
        Dict mapping chunk_id to score
    """
    import math
    
    scores: Dict[str, float] = {}
    anchor_terms_set = set(anchor_terms) if anchor_terms else set()
    
    if not use_idf:
        # Legacy mode: each term adds 1.0
        for result in term_results:
            for chunk_id in result.chunk_ids:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0
    else:
        # IDF mode: score based on which tokens actually appear in each chunk
        # Collect all tokens, bigrams, and phrases from search terms
        all_tokens: Set[str] = set()
        all_bigrams: Set[str] = set()
        all_phrases: Set[str] = set()
        
        for result in term_results:
            all_tokens.update(result.matched_tokens)
            all_bigrams.update(result.matched_bigrams)
            all_phrases.update(result.matched_phrases)
        
        # For each chunk found, compute score based on which tokens it contains
        all_chunk_ids: Set[str] = set()
        chunk_match_counts: Dict[str, int] = {}  # Track number of matches per chunk
        
        for result in term_results:
            all_chunk_ids.update(result.chunk_ids)
        
        for chunk_id in all_chunk_ids:
            chunk_score = 0.0
            match_count = 0
            
            # Score tokens that this chunk actually contains
            for token in all_tokens:
                if chunk_id in index.term_to_chunks.get(token, set()):
                    base_idf = index.term_idf.get(token, 1.0)
                    # Apply anchor term multiplier for priority terms
                    if token in anchor_terms_set:
                        chunk_score += base_idf * anchor_term_multiplier
                    else:
                        chunk_score += base_idf
                    match_count += 1
            
            # Score bigrams that this chunk actually contains (with bonus)
            for bigram in all_bigrams:
                if chunk_id in index.bigram_to_chunks.get(bigram, set()):
                    chunk_score += index.bigram_idf.get(bigram, 1.0) * BIGRAM_BONUS
                    match_count += 1
            
            # Score exact phrases that this chunk contains (highest bonus)
            for phrase in all_phrases:
                if chunk_id in index.bigram_to_chunks.get(phrase, set()):
                    chunk_score += index.bigram_idf.get(phrase, 1.0) * EXACT_PHRASE_BONUS
                    match_count += 1
            
            # Apply diminishing returns penalty for chunks with too many matches
            # This helps prevent generic content (matching many terms) from dominating
            if match_count > max_term_match_threshold:
                penalty = 1.0 / (1.0 + math.log(match_count - max_term_match_threshold + 1))
                chunk_score *= penalty
            
            scores[chunk_id] = chunk_score
            chunk_match_counts[chunk_id] = match_count
    
    # Apply anchor bonus
    if anchor_chunk_ids:
        for chunk_id in anchor_chunk_ids:
            if chunk_id in scores:
                scores[chunk_id] += anchor_bonus
    
    return scores


def execute_parallel_search(
    terms: List[str],
    index: TraversalIndex,
    original_query: Optional[str] = None,
    anchor_bonus: float = 2.0,
    anchor_terms: Optional[List[str]] = None,
    anchor_term_multiplier: float = 2.0,
    max_term_match_threshold: int = 6,
    max_workers: int = 5,
    use_idf: bool = True,
) -> ParallelSearchResult:
    """
    Execute parallel search for multiple terms and combine results.
    
    Args:
        terms: List of expanded search terms
        index: TraversalIndex to search
        original_query: Optional original query for anchor identification
        anchor_bonus: Score bonus for chunks matching original query
        anchor_terms: List of anchor terms from original query (priority weighting)
        anchor_term_multiplier: Multiplier for anchor term IDF (default 2.0)
        max_term_match_threshold: Threshold above which diminishing returns applies (default 6)
        max_workers: Maximum parallel threads
        use_idf: Whether to use IDF weighting (default True, set False for legacy scoring)
        
    Returns:
        ParallelSearchResult with combined chunks and scores
    """
    start = time.perf_counter()
    
    # Search all terms
    term_results = search_terms_parallel(terms, index, max_workers)
    
    # Combine all chunk IDs
    combined_chunks: Set[str] = set()
    for result in term_results:
        combined_chunks |= result.chunk_ids
    
    # Find anchors from original query if provided
    anchor_chunk_ids: Optional[Set[str]] = None
    if original_query:
        anchor_result = search_term(original_query, index)
        anchor_chunk_ids = anchor_result.chunk_ids
    
    # Extract anchor terms from original query if not provided
    effective_anchor_terms = anchor_terms
    if effective_anchor_terms is None and original_query:
        effective_anchor_terms = tokenize_and_normalize(original_query)
    
    # Compute scores with IDF weighting
    chunk_scores = compute_chunk_scores(
        term_results,
        index=index,
        anchor_bonus=anchor_bonus,
        anchor_chunk_ids=anchor_chunk_ids,
        anchor_terms=effective_anchor_terms,
        anchor_term_multiplier=anchor_term_multiplier,
        max_term_match_threshold=max_term_match_threshold,
        use_idf=use_idf,
    )
    
    total_latency_ms = (time.perf_counter() - start) * 1000
    
    # Compute stats
    terms_with_hits = sum(1 for r in term_results if r.hit_count > 0)
    total_hits = sum(r.hit_count for r in term_results)
    total_idf = sum(r.idf_score for r in term_results)
    bigram_matches = sum(len(r.matched_bigrams) for r in term_results)
    phrase_matches = sum(len(r.matched_phrases) for r in term_results)
    
    search_stats = {
        "total_terms": len(terms),
        "terms_with_hits": terms_with_hits,
        "term_hit_rate": terms_with_hits / max(1, len(terms)),
        "total_hits": total_hits,
        "unique_chunks": len(combined_chunks),
        "dedup_ratio": len(combined_chunks) / max(1, total_hits),
        "search_types": {r.search_type: sum(1 for x in term_results if x.search_type == r.search_type) for r in term_results},
        "use_idf": use_idf,
        "total_idf_score": total_idf,
        "avg_idf_per_term": total_idf / max(1, len(terms)),
        "bigram_matches": bigram_matches,
        "phrase_matches": phrase_matches,
        "anchor_term_multiplier": anchor_term_multiplier,
        "max_term_match_threshold": max_term_match_threshold,
    }
    
    return ParallelSearchResult(
        query_terms=terms,
        term_results=term_results,
        combined_chunks=combined_chunks,
        chunk_scores=chunk_scores,
        total_latency_ms=total_latency_ms,
        search_stats=search_stats,
    )


def get_top_k_chunks(
    search_result: ParallelSearchResult,
    index: TraversalIndex,
    k: int = 30,
) -> List[Dict[str, Any]]:
    """
    Get top-k chunks from parallel search result, sorted by score.
    
    Args:
        search_result: ParallelSearchResult from execute_parallel_search
        index: TraversalIndex (for chunk metadata)
        k: Number of top chunks to return
        
    Returns:
        List of chunk dicts with scores, sorted by score descending
    """
    # Sort chunks by score
    sorted_chunks = sorted(
        search_result.chunk_scores.items(),
        key=lambda x: -x[1]
    )
    
    results = []
    for chunk_id, score in sorted_chunks[:k]:
        chunk = index.chunk_by_id.get(chunk_id)
        if chunk:
            results.append({
                "chunk_id": chunk_id,
                "chunk": chunk,
                "deterministic_score": score,
                "terms_matched": sum(
                    1 for r in search_result.term_results
                    if chunk_id in r.chunk_ids
                ),
            })
    
    return results
