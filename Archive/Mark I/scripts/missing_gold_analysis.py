#!/usr/bin/env python3
"""
Missing Gold Chunks Analysis

Diagnoses why 57% of gold chunks are NOT found by ANY retrieval pipeline.
Categorizes each missing chunk by root cause:
  - Not indexed (tokenization filtering)
  - Not embedded
  - Query mismatch (expansion missed terms)
  - Semantic gap (low similarity)
  - Graph disconnect

Run from RulesIngestion directory:
    uv run python scripts/missing_gold_analysis.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

# Load environment variables from parent .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env.development"
if env_path.exists():
    load_dotenv(env_path)
    print(f"📝 Loaded environment from: {env_path}")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from traversal import (
    TraversalIndex,
    HybridConfig,
    HybridRetriever,
    DEFAULT_EXPANSION_MODEL,
)
from traversal.index import tokenize_and_normalize
from traversal.expander import QueryExpander


# Configuration
ENRICHED_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
GRAPH_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json")
EVAL_QUERIES_PATH = Path("blind_eval/batches/batch_001.json")
OUTPUT_DIR = Path("scripts/analysis_results")


@dataclass
class MissingChunkAnalysis:
    """Analysis for a gold chunk not found by any pipeline."""
    query_id: str
    query_text: str
    chunk_id: str
    chunk_text_preview: str
    
    # Index coverage
    in_term_index: bool
    in_section_index: bool
    in_content_kind_index: bool
    in_tag_index: bool
    in_trait_index: bool
    in_entity_index: bool
    in_bigram_index: bool
    in_embeddings: bool  # If semantic search is enabled
    
    # Token analysis
    chunk_tokens: List[str]
    expansion_tokens: List[str]
    overlapping_tokens: List[str]
    token_overlap_count: int
    token_overlap_ratio: float
    
    # Semantic analysis (if available)
    semantic_rank: Optional[int]
    semantic_score: Optional[float]
    
    # Root cause
    root_cause: str
    root_cause_details: str


def load_enriched_chunks(path: Path) -> list:
    """Load enriched chunks from JSON file."""
    print(f"📂 Loading enriched data from: {path}")
    with open(path) as f:
        data = json.load(f)
    
    if isinstance(data, list):
        chunks = data
    elif isinstance(data, dict) and "chunks" in data:
        chunks = data["chunks"]
    else:
        chunks = list(data.values()) if isinstance(data, dict) else []
    
    print(f"   Loaded {len(chunks)} chunks")
    return chunks


def load_graph(path: Path) -> dict:
    """Load graph from JSON file."""
    print(f"📂 Loading graph from: {path}")
    with open(path) as f:
        data = json.load(f)
    
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"   Loaded {len(nodes)} nodes, {len(edges)} edges")
    return data


def load_eval_queries(path: Path) -> List[Dict[str, Any]]:
    """Load evaluation queries with gold chunks."""
    print(f"📂 Loading evaluation queries from: {path}")
    with open(path) as f:
        data = json.load(f)
    
    queries = []
    for q in data.get("queries", []):
        # Skip incomplete queries
        if "TODO" in q.get("question", "") or any("TODO" in g for g in q.get("gold_chunk_ids", [])):
            continue
        queries.append({
            "query_id": q["id"],
            "query_text": q["question"],
            "gold_chunk_ids": set(q["gold_chunk_ids"]),
        })
    
    print(f"   Loaded {len(queries)} complete queries")
    return queries


def create_semantic_search_fn(chunks: List[Dict], index: TraversalIndex):
    """Create a semantic search function using sentence-transformers."""
    from sentence_transformers import SentenceTransformer
    
    print("🧠 Loading sentence-transformers model for semantic search...")
    model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
    
    # Build chunk ID list and text list
    chunk_ids = []
    chunk_texts = []
    for chunk in chunks:
        chunk_id = chunk.get("id")
        text = chunk.get("text", "")
        if chunk_id and text:
            chunk_ids.append(chunk_id)
            chunk_texts.append(text)
    
    print(f"   Encoding {len(chunk_texts)} chunks...")
    chunk_embeddings = model.encode(chunk_texts, show_progress_bar=True)
    print(f"   Embeddings shape: {chunk_embeddings.shape}")
    
    # Create chunk lookup
    chunk_by_id = {chunk.get("id"): chunk for chunk in chunks}
    
    def semantic_search(query: str, k: int) -> List[Dict[str, Any]]:
        """Search using sentence embeddings."""
        query_embedding = model.encode([query])[0]
        
        # Compute cosine similarities
        similarities = chunk_embeddings @ query_embedding / (
            np.linalg.norm(chunk_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:k]
        
        results = []
        for idx in top_indices:
            chunk_id = chunk_ids[idx]
            results.append({
                "chunk_id": chunk_id,
                "chunk": chunk_by_id.get(chunk_id, {}),
                "semantic_score": float(similarities[idx]),
            })
        
        return results
    
    def get_chunk_semantic_rank_and_score(query: str, target_chunk_id: str) -> Tuple[Optional[int], Optional[float]]:
        """Get the semantic rank and score for a specific chunk given a query."""
        query_embedding = model.encode([query])[0]
        
        # Compute cosine similarities
        similarities = chunk_embeddings @ query_embedding / (
            np.linalg.norm(chunk_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Find the target chunk
        if target_chunk_id in chunk_ids:
            idx = chunk_ids.index(target_chunk_id)
            score = float(similarities[idx])
            # Compute rank
            rank = int(np.sum(similarities > score)) + 1
            return rank, score
        
        return None, None
    
    return semantic_search, get_chunk_semantic_rank_and_score


def check_chunk_indexing(chunk_id: str, chunk: Dict, index: TraversalIndex) -> Dict[str, Any]:
    """Check if a chunk is indexed in various ways."""
    text = chunk.get("text", "")
    tokens = tokenize_and_normalize(text)
    
    # Check term index
    in_term_index = False
    indexed_tokens = []
    for token in tokens:
        if token in index.term_to_chunks:
            if chunk_id in index.term_to_chunks[token]:
                in_term_index = True
                indexed_tokens.append(token)
    
    # Check section index
    in_section_index = False
    section_path = chunk.get("section_path", [])
    for title in section_path:
        title_lower = title.lower().strip()
        if title_lower in index.section_title_to_chunks:
            if chunk_id in index.section_title_to_chunks[title_lower]:
                in_section_index = True
                break
    
    # Check content kind
    in_content_kind_index = False
    content_kind = chunk.get("content_kind", "")
    if content_kind:
        kind_lower = content_kind.lower()
        if kind_lower in index.content_kind_to_chunks:
            if chunk_id in index.content_kind_to_chunks[kind_lower]:
                in_content_kind_index = True
    
    # Check tags
    in_tag_index = False
    for tag in chunk.get("tags", []):
        tag_lower = tag.lower().strip()
        if tag_lower in index.tag_to_chunks:
            if chunk_id in index.tag_to_chunks[tag_lower]:
                in_tag_index = True
                break
    
    # Check traits
    in_trait_index = False
    for trait in chunk.get("traits", []):
        trait_lower = trait.lower().strip()
        if trait_lower in index.trait_to_chunks:
            if chunk_id in index.trait_to_chunks[trait_lower]:
                in_trait_index = True
                break
    
    # Check entity index
    in_entity_index = chunk_id in index.entity_to_chunks
    
    # Check bigram index
    in_bigram_index = False
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i+1]}"
        if bigram in index.bigram_to_chunks:
            if chunk_id in index.bigram_to_chunks[bigram]:
                in_bigram_index = True
                break
    
    return {
        "in_term_index": in_term_index,
        "in_section_index": in_section_index,
        "in_content_kind_index": in_content_kind_index,
        "in_tag_index": in_tag_index,
        "in_trait_index": in_trait_index,
        "in_entity_index": in_entity_index,
        "in_bigram_index": in_bigram_index,
        "indexed_tokens": indexed_tokens,
        "chunk_tokens": tokens,
    }


def analyze_token_overlap(
    chunk_tokens: List[str],
    expansion_tokens: List[str],
) -> Dict[str, Any]:
    """Analyze overlap between chunk tokens and expansion tokens."""
    chunk_token_set = set(chunk_tokens)
    expansion_token_set = set(expansion_tokens)
    
    overlapping = chunk_token_set & expansion_token_set
    
    return {
        "overlapping_tokens": list(overlapping),
        "token_overlap_count": len(overlapping),
        "token_overlap_ratio": len(overlapping) / max(1, len(expansion_token_set)),
        "chunk_unique_tokens": list(chunk_token_set - expansion_token_set),
        "expansion_unique_tokens": list(expansion_token_set - chunk_token_set),
    }


def determine_root_cause(
    indexing: Dict[str, Any],
    token_analysis: Dict[str, Any],
    semantic_rank: Optional[int],
    semantic_score: Optional[float],
    total_chunks: int,
) -> Tuple[str, str]:
    """Determine the root cause for why a chunk wasn't found."""
    
    # Check if it's not indexed at all
    if not indexing["in_term_index"]:
        return "NOT_INDEXED", "Chunk tokens not in term_to_chunks index (tokenization filtered them)"
    
    # Check if expansion missed the terms
    if token_analysis["token_overlap_count"] == 0:
        return "QUERY_MISMATCH", f"Zero token overlap between chunk ({len(indexing['chunk_tokens'])} tokens) and expansion ({len(token_analysis['expansion_unique_tokens'])} tokens)"
    
    # Check semantic gap
    if semantic_rank is not None:
        semantic_percentile = (semantic_rank / total_chunks) * 100
        if semantic_percentile > 50:  # Bottom 50%
            return "SEMANTIC_GAP", f"Low semantic similarity - ranked {semantic_rank}/{total_chunks} ({semantic_percentile:.1f}th percentile), score={semantic_score:.4f}"
    
    # Low overlap but some tokens match
    if token_analysis["token_overlap_ratio"] < 0.3:
        return "LOW_OVERLAP", f"Only {token_analysis['token_overlap_count']} tokens overlap ({token_analysis['token_overlap_ratio']:.1%}) - expansion needs more specific terms"
    
    # Chunk is indexed and has overlap, but still not retrieved
    # This suggests the scoring didn't rank it high enough
    return "SCORING_GAP", f"Chunk indexed with {token_analysis['token_overlap_count']} matching tokens but scored too low for retrieval pool"


def main():
    print("=" * 70)
    print("🔍 MISSING GOLD CHUNKS ANALYSIS")
    print("=" * 70)
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Load data
    chunks = load_enriched_chunks(ENRICHED_DATA_PATH)
    graph = load_graph(GRAPH_DATA_PATH)
    queries = load_eval_queries(EVAL_QUERIES_PATH)
    
    # Build chunk lookup
    chunk_by_id = {c.get("id"): c for c in chunks}
    
    # Build index
    print("🔨 Building TraversalIndex...")
    index = TraversalIndex.build(graph, chunks)
    print(f"   Index: {index.total_chunks} chunks, {len(index.term_to_chunks)} terms")
    print()
    
    # Create semantic search function
    semantic_search_fn, get_semantic_rank_fn = create_semantic_search_fn(chunks, index)
    
    # Create retriever
    config = HybridConfig(
        expansion_model=DEFAULT_EXPANSION_MODEL,
        deterministic_weight=0.5,
        semantic_weight=0.5,
        expansion_terms=7,
        top_k=200,  # Larger pool to find more
        enable_semantic=True,
        semantic_search_fn=semantic_search_fn,
        use_idf=True,
    )
    
    retriever = HybridRetriever(index, config)
    
    # Create query expander
    expander = QueryExpander()
    
    print("=" * 70)
    print("🧪 Finding missing gold chunks across all queries...")
    print("=" * 70)
    print()
    
    all_missing_analyses: List[MissingChunkAnalysis] = []
    all_gold_ids: Set[str] = set()
    all_found_ids: Set[str] = set()
    
    # Root cause counts
    root_cause_counts: Dict[str, int] = defaultdict(int)
    
    for query in queries:
        print(f"📋 Query: {query['query_id']}")
        print(f"   {query['query_text'][:60]}...")
        
        query_text = query["query_text"]
        gold_ids = query["gold_chunk_ids"]
        all_gold_ids.update(gold_ids)
        
        # Run retrieval
        result = retriever.retrieve(query_text, gold_chunk_ids=gold_ids)
        
        # Get found chunk IDs
        found_ids = {c.chunk_id for c in result.ranked_chunks}
        all_found_ids.update(found_ids)
        
        # Get expansion terms
        expansion_result = expander.expand(query_text)
        expansion_terms = expansion_result.expanded_terms
        
        # Tokenize expansion terms
        expansion_tokens = []
        for term in expansion_terms:
            expansion_tokens.extend(tokenize_and_normalize(term))
        expansion_tokens = list(set(expansion_tokens))
        
        # Find missing gold chunks
        missing_ids = gold_ids - found_ids
        found_count = len(gold_ids) - len(missing_ids)
        
        print(f"   Found: {found_count}/{len(gold_ids)} gold chunks")
        print(f"   Missing: {len(missing_ids)} chunks")
        
        for chunk_id in missing_ids:
            chunk = chunk_by_id.get(chunk_id, {})
            if not chunk:
                print(f"   ⚠️ Chunk not in lookup: {chunk_id}")
                continue
            
            # Check indexing
            indexing = check_chunk_indexing(chunk_id, chunk, index)
            
            # Analyze token overlap
            token_analysis = analyze_token_overlap(
                indexing["chunk_tokens"],
                expansion_tokens,
            )
            
            # Get semantic rank
            semantic_rank, semantic_score = get_semantic_rank_fn(query_text, chunk_id)
            
            # Determine root cause
            root_cause, root_cause_details = determine_root_cause(
                indexing,
                token_analysis,
                semantic_rank,
                semantic_score,
                len(chunks),
            )
            
            root_cause_counts[root_cause] += 1
            
            analysis = MissingChunkAnalysis(
                query_id=query["query_id"],
                query_text=query_text[:80],
                chunk_id=chunk_id,
                chunk_text_preview=chunk.get("text", "")[:100],
                in_term_index=indexing["in_term_index"],
                in_section_index=indexing["in_section_index"],
                in_content_kind_index=indexing["in_content_kind_index"],
                in_tag_index=indexing["in_tag_index"],
                in_trait_index=indexing["in_trait_index"],
                in_entity_index=indexing["in_entity_index"],
                in_bigram_index=indexing["in_bigram_index"],
                in_embeddings=semantic_rank is not None,
                chunk_tokens=indexing["chunk_tokens"][:20],  # Limit for output
                expansion_tokens=expansion_tokens[:20],
                overlapping_tokens=token_analysis["overlapping_tokens"],
                token_overlap_count=token_analysis["token_overlap_count"],
                token_overlap_ratio=token_analysis["token_overlap_ratio"],
                semantic_rank=semantic_rank,
                semantic_score=semantic_score,
                root_cause=root_cause,
                root_cause_details=root_cause_details,
            )
            
            all_missing_analyses.append(analysis)
            
            print(f"      ❌ {chunk_id[:50]}...")
            print(f"         Root cause: {root_cause}")
        
        print()
    
    # Summary
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    total_gold = len(all_gold_ids)
    total_found = len(all_gold_ids & all_found_ids)
    total_missing = len(all_missing_analyses)
    
    print(f"Total gold chunks: {total_gold}")
    print(f"  Found by pipeline: {total_found} ({100*total_found/total_gold:.1f}%)")
    print(f"  Missing (analyzed): {total_missing} ({100*total_missing/total_gold:.1f}%)")
    print()
    
    # Root cause breakdown
    print("=" * 70)
    print("🔴 ROOT CAUSE BREAKDOWN")
    print("=" * 70)
    print()
    
    for root_cause, count in sorted(root_cause_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / total_missing
        print(f"  {root_cause}: {count} ({pct:.1f}%)")
    
    print()
    
    # Detailed analysis by root cause
    print("=" * 70)
    print("🔍 DETAILED ANALYSIS BY ROOT CAUSE")
    print("=" * 70)
    
    for root_cause in sorted(root_cause_counts.keys()):
        analyses = [a for a in all_missing_analyses if a.root_cause == root_cause]
        print(f"\n### {root_cause} ({len(analyses)} chunks)")
        print("-" * 50)
        
        for analysis in analyses[:5]:  # Show up to 5 examples per cause
            print(f"\n  Query: {analysis.query_id}")
            print(f"  Chunk: {analysis.chunk_id[:60]}...")
            print(f"  Text: \"{analysis.chunk_text_preview}...\"")
            print(f"  Details: {analysis.root_cause_details}")
            print(f"  Token overlap: {analysis.token_overlap_count} ({analysis.token_overlap_ratio:.1%})")
            if analysis.semantic_rank:
                print(f"  Semantic rank: {analysis.semantic_rank} (score={analysis.semantic_score:.4f})")
            print(f"  Indexed in: term={analysis.in_term_index}, section={analysis.in_section_index}, "
                  f"bigram={analysis.in_bigram_index}")
    
    # Recommendations
    print()
    print("=" * 70)
    print("🚀 RECOMMENDATIONS")
    print("=" * 70)
    print()
    
    if root_cause_counts.get("NOT_INDEXED", 0) > 0:
        print("1. NOT_INDEXED: Review tokenization in index.py")
        print("   - Check STOPWORDS list for game-specific terms")
        print("   - Consider lowering min token length from 2 to 1")
        print()
    
    if root_cause_counts.get("QUERY_MISMATCH", 0) > 0:
        print("2. QUERY_MISMATCH: Improve query expansion")
        print("   - Add more domain-specific few-shot examples")
        print("   - Consider extracting key terms from gold chunks")
        print("   - Add anchor term extraction from original query")
        print()
    
    if root_cause_counts.get("SEMANTIC_GAP", 0) > 0:
        print("3. SEMANTIC_GAP: Improve semantic search")
        print("   - Increase semantic top_k to retrieve more candidates")
        print("   - Consider domain-specific embedding fine-tuning")
        print()
    
    if root_cause_counts.get("LOW_OVERLAP", 0) > 0:
        print("4. LOW_OVERLAP: Expand term coverage")
        print("   - Add synonym expansion")
        print("   - Consider BM25 scoring for partial matches")
        print()
    
    if root_cause_counts.get("SCORING_GAP", 0) > 0:
        print("5. SCORING_GAP: Tune scoring weights")
        print("   - Increase anchor_bonus for original query matches")
        print("   - Add anchor term weighting in IDF scoring")
        print()
    
    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"missing_gold_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_gold": total_gold,
            "found": total_found,
            "missing": total_missing,
            "found_pct": 100 * total_found / total_gold,
            "missing_pct": 100 * total_missing / total_gold,
        },
        "root_cause_breakdown": dict(root_cause_counts),
        "missing_chunks": [
            {
                "query_id": a.query_id,
                "chunk_id": a.chunk_id,
                "chunk_text_preview": a.chunk_text_preview,
                "root_cause": a.root_cause,
                "root_cause_details": a.root_cause_details,
                "token_overlap_count": a.token_overlap_count,
                "token_overlap_ratio": a.token_overlap_ratio,
                "semantic_rank": a.semantic_rank,
                "semantic_score": a.semantic_score,
                "in_term_index": a.in_term_index,
                "in_section_index": a.in_section_index,
                "in_bigram_index": a.in_bigram_index,
                "overlapping_tokens": a.overlapping_tokens,
            }
            for a in all_missing_analyses
        ],
    }
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📁 Results saved to: {output_file}")
    
    print()
    print("=" * 70)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
