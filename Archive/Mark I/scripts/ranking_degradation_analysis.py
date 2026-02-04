#!/usr/bin/env python3
"""
Ranking Degradation Analysis

Diagnoses why gold chunks are being found but ranked poorly (position 30+)
in the Weighted Sum hybrid retrieval pipeline.

Run from RulesIngestion directory:
    uv run python scripts/ranking_degradation_analysis.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

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
    RerankConfig,
    RerankStrategy,
    DEFAULT_EXPANSION_MODEL,
)
from traversal.reranker import normalize_scores, RankedChunk


# Configuration
ENRICHED_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
GRAPH_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json")
EVAL_QUERIES_PATH = Path("blind_eval/batches/batch_001.json")
OUTPUT_DIR = Path("scripts/analysis_results")


@dataclass
class LowRankedGoldAnalysis:
    """Analysis for a gold chunk ranked 30+."""
    query_id: str
    query_text: str
    chunk_id: str
    rank: int
    det_score_raw: float
    sem_score_raw: float
    det_score_normalized: float
    sem_score_normalized: float
    final_score: float
    found_by: str
    is_anchor: bool
    terms_matched: int
    # What beat it
    beaten_by: List[Dict[str, Any]]


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
    """Create a mock semantic search function using TF-IDF-like scoring."""
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
    
    return semantic_search


def analyze_query_ranking(
    query: Dict[str, Any],
    retriever: HybridRetriever,
    det_scores_raw: Dict[str, float],
    sem_scores_raw: Dict[str, float],
) -> Tuple[List[LowRankedGoldAnalysis], Dict[str, Any]]:
    """Analyze ranking for a single query."""
    query_id = query["query_id"]
    query_text = query["query_text"]
    gold_ids = query["gold_chunk_ids"]
    
    # Run retrieval
    result = retriever.retrieve(query_text, gold_chunk_ids=gold_ids)
    
    # Compute normalized scores (same as reranker does)
    det_scores_norm = normalize_scores(det_scores_raw)
    sem_scores_norm = normalize_scores(sem_scores_raw)
    
    # Find low-ranked gold chunks (rank > 30)
    low_ranked_analyses = []
    gold_in_top_30 = []
    gold_found = []
    gold_not_found = []
    
    # Check all ranked chunks for gold
    all_ranked_ids = {c.chunk_id for c in result.ranked_chunks}
    
    for chunk in result.ranked_chunks:
        if chunk.chunk_id in gold_ids:
            gold_found.append(chunk)
            if chunk.rank <= 30:
                gold_in_top_30.append(chunk)
            else:
                # Get what beat this gold chunk
                beaten_by = []
                for top_chunk in result.ranked_chunks[:30]:
                    if top_chunk.chunk_id not in gold_ids:
                        beaten_by.append({
                            "chunk_id": top_chunk.chunk_id,
                            "rank": top_chunk.rank,
                            "det_raw": top_chunk.deterministic_score,
                            "sem_raw": top_chunk.semantic_score,
                            "det_norm": det_scores_norm.get(top_chunk.chunk_id, 0.0),
                            "sem_norm": sem_scores_norm.get(top_chunk.chunk_id, 0.0),
                            "final": top_chunk.final_score,
                            "found_by": top_chunk.found_by,
                        })
                
                analysis = LowRankedGoldAnalysis(
                    query_id=query_id,
                    query_text=query_text[:80],
                    chunk_id=chunk.chunk_id,
                    rank=chunk.rank,
                    det_score_raw=chunk.deterministic_score,
                    sem_score_raw=chunk.semantic_score,
                    det_score_normalized=det_scores_norm.get(chunk.chunk_id, 0.0),
                    sem_score_normalized=sem_scores_norm.get(chunk.chunk_id, 0.0),
                    final_score=chunk.final_score,
                    found_by=chunk.found_by,
                    is_anchor=chunk.is_anchor,
                    terms_matched=chunk.terms_matched,
                    beaten_by=beaten_by[:5],  # Top 5 non-gold that beat it
                )
                low_ranked_analyses.append(analysis)
    
    # Check for gold not found at all
    for gold_id in gold_ids:
        if gold_id not in all_ranked_ids:
            gold_not_found.append(gold_id)
    
    # Compute statistics
    stats = {
        "query_id": query_id,
        "gold_count": len(gold_ids),
        "gold_found": len(gold_found),
        "gold_not_found": len(gold_not_found),
        "gold_in_top_30": len(gold_in_top_30),
        "gold_ranked_30_plus": len(low_ranked_analyses),
        "gold_ranks": [c.rank for c in gold_found],
    }
    
    return low_ranked_analyses, stats


def compute_score_distributions(
    result_chunks: List[RankedChunk],
    gold_ids: Set[str],
) -> Dict[str, Any]:
    """Compute score distributions for gold vs non-gold chunks."""
    gold_det = []
    gold_sem = []
    gold_final = []
    nongold_det = []
    nongold_sem = []
    nongold_final = []
    
    for chunk in result_chunks:
        if chunk.chunk_id in gold_ids:
            gold_det.append(chunk.deterministic_score)
            gold_sem.append(chunk.semantic_score)
            gold_final.append(chunk.final_score)
        else:
            nongold_det.append(chunk.deterministic_score)
            nongold_sem.append(chunk.semantic_score)
            nongold_final.append(chunk.final_score)
    
    def stats(arr):
        if not arr:
            return {"mean": 0, "median": 0, "std": 0, "min": 0, "max": 0}
        return {
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }
    
    return {
        "gold_det": stats(gold_det),
        "gold_sem": stats(gold_sem),
        "gold_final": stats(gold_final),
        "nongold_det": stats(nongold_det),
        "nongold_sem": stats(nongold_sem),
        "nongold_final": stats(nongold_final),
        "gold_count": len(gold_det),
        "nongold_count": len(nongold_det),
    }


def main():
    print("=" * 70)
    print("🔍 RANKING DEGRADATION ANALYSIS")
    print("=" * 70)
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Load data
    chunks = load_enriched_chunks(ENRICHED_DATA_PATH)
    graph = load_graph(GRAPH_DATA_PATH)
    queries = load_eval_queries(EVAL_QUERIES_PATH)
    
    # Build index
    print("🔨 Building TraversalIndex...")
    index = TraversalIndex.build(graph, chunks)
    print(f"   Index: {index.total_chunks} chunks, {len(index.term_to_chunks)} terms")
    print()
    
    # Create semantic search function
    semantic_search_fn = create_semantic_search_fn(chunks, index)
    
    # Create retriever with Weighted Sum (the problem case)
    config = HybridConfig(
        expansion_model=DEFAULT_EXPANSION_MODEL,
        deterministic_weight=0.5,
        semantic_weight=0.5,
        expansion_terms=7,
        top_k=100,  # Get more results to see where gold ranks
        enable_semantic=True,
        semantic_search_fn=semantic_search_fn,
        use_idf=True,
        fusion_strategy="weighted_sum",
    )
    
    retriever = HybridRetriever(index, config)
    
    print("=" * 70)
    print("🧪 Running Weighted Sum pipeline on evaluation queries...")
    print("=" * 70)
    print()
    
    all_low_ranked = []
    all_stats = []
    all_distributions = []
    
    for query in queries:
        print(f"📋 Query: {query['query_id']}")
        print(f"   {query['query_text'][:60]}...")
        
        result = retriever.retrieve(query["query_text"], gold_chunk_ids=query["gold_chunk_ids"])
        
        # Get raw scores for analysis
        det_scores_raw = {}
        sem_scores_raw = {}
        
        if result.parallel_search_result:
            det_scores_raw = result.parallel_search_result.chunk_scores
        
        if result.rerank_result:
            for chunk in result.rerank_result.ranked_chunks:
                sem_scores_raw[chunk.chunk_id] = chunk.semantic_score
        
        # Analyze
        low_ranked, stats = analyze_query_ranking(
            query, retriever, det_scores_raw, sem_scores_raw
        )
        all_low_ranked.extend(low_ranked)
        all_stats.append(stats)
        
        # Score distributions
        dist = compute_score_distributions(
            result.rerank_result.ranked_chunks if result.rerank_result else result.ranked_chunks,
            query["gold_chunk_ids"],
        )
        all_distributions.append(dist)
        
        print(f"   Gold: {stats['gold_found']}/{stats['gold_count']} found, "
              f"{stats['gold_in_top_30']} in top 30, "
              f"{stats['gold_ranked_30_plus']} ranked 30+")
        if stats['gold_ranks']:
            print(f"   Gold ranks: {stats['gold_ranks']}")
        print()
    
    # Summary
    print("=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    total_gold = sum(s["gold_count"] for s in all_stats)
    total_found = sum(s["gold_found"] for s in all_stats)
    total_top_30 = sum(s["gold_in_top_30"] for s in all_stats)
    total_30_plus = sum(s["gold_ranked_30_plus"] for s in all_stats)
    total_not_found = sum(s["gold_not_found"] for s in all_stats)
    
    print(f"Total gold chunks: {total_gold}")
    print(f"  Found by pipeline: {total_found} ({100*total_found/total_gold:.1f}%)")
    print(f"  In top 30: {total_top_30} ({100*total_top_30/total_gold:.1f}%)")
    print(f"  Ranked 30+: {total_30_plus} ({100*total_30_plus/total_gold:.1f}%)")
    print(f"  Not found at all: {total_not_found} ({100*total_not_found/total_gold:.1f}%)")
    print()
    
    # Low-ranked gold analysis
    if all_low_ranked:
        print("=" * 70)
        print("🔴 LOW-RANKED GOLD CHUNKS (ranked 30+)")
        print("=" * 70)
        
        for analysis in all_low_ranked:
            print(f"\n📌 {analysis.query_id} | Rank: {analysis.rank}")
            print(f"   Chunk: {analysis.chunk_id[:60]}...")
            print(f"   Det Raw: {analysis.det_score_raw:.4f} | Sem Raw: {analysis.sem_score_raw:.4f}")
            print(f"   Det Norm: {analysis.det_score_normalized:.4f} | Sem Norm: {analysis.sem_score_normalized:.4f}")
            print(f"   Final: {analysis.final_score:.4f}")
            print(f"   Found by: {analysis.found_by} | Anchor: {analysis.is_anchor}")
            print(f"   Terms matched: {analysis.terms_matched}")
            
            if analysis.beaten_by:
                print("   Beaten by (top 5 non-gold):")
                for b in analysis.beaten_by[:3]:
                    print(f"      Rank {b['rank']}: det={b['det_raw']:.4f}, "
                          f"sem={b['sem_raw']:.4f}, final={b['final']:.4f}, "
                          f"via={b['found_by']}")
    
    # Score distribution analysis
    print()
    print("=" * 70)
    print("📊 SCORE DISTRIBUTIONS (Gold vs Non-Gold)")
    print("=" * 70)
    
    # Aggregate distributions
    gold_det_all = []
    gold_sem_all = []
    gold_final_all = []
    nongold_det_all = []
    nongold_sem_all = []
    nongold_final_all = []
    
    for query, dist in zip(queries, all_distributions):
        # Re-run to get actual values
        result = retriever.retrieve(query["query_text"], gold_chunk_ids=query["gold_chunk_ids"])
        for chunk in result.ranked_chunks:
            if chunk.chunk_id in query["gold_chunk_ids"]:
                gold_det_all.append(chunk.deterministic_score)
                gold_sem_all.append(chunk.semantic_score)
                gold_final_all.append(chunk.final_score)
            else:
                nongold_det_all.append(chunk.deterministic_score)
                nongold_sem_all.append(chunk.semantic_score)
                nongold_final_all.append(chunk.final_score)
    
    def print_comparison(name: str, gold: List[float], nongold: List[float]):
        if not gold:
            print(f"{name}: No gold data")
            return
        print(f"{name}:")
        print(f"   Gold (n={len(gold)}):    mean={np.mean(gold):.4f}, "
              f"median={np.median(gold):.4f}, std={np.std(gold):.4f}")
        print(f"   Non-gold (n={len(nongold)}): mean={np.mean(nongold):.4f}, "
              f"median={np.median(nongold):.4f}, std={np.std(nongold):.4f}")
        
        # Hypothesis: are gold scores significantly different?
        if gold and nongold:
            gold_mean = np.mean(gold)
            nongold_mean = np.mean(nongold)
            diff = gold_mean - nongold_mean
            print(f"   Difference: {diff:+.4f} ({'gold higher' if diff > 0 else 'NON-GOLD HIGHER ⚠️'})")
    
    print()
    print_comparison("Deterministic Score", gold_det_all, nongold_det_all)
    print()
    print_comparison("Semantic Score", gold_sem_all, nongold_sem_all)
    print()
    print_comparison("Final Score", gold_final_all, nongold_final_all)
    
    # Root cause hypotheses
    print()
    print("=" * 70)
    print("🎯 ROOT CAUSE HYPOTHESES")
    print("=" * 70)
    
    # Check normalization impact
    if gold_det_all and nongold_det_all:
        det_gold_mean = np.mean(gold_det_all)
        det_nongold_mean = np.mean(nongold_det_all)
        
        sem_gold_mean = np.mean(gold_sem_all) if gold_sem_all else 0
        sem_nongold_mean = np.mean(nongold_sem_all) if nongold_sem_all else 0
        
        final_gold_mean = np.mean(gold_final_all) if gold_final_all else 0
        final_nongold_mean = np.mean(nongold_final_all) if nongold_final_all else 0
        
        print()
        print("1. NORMALIZATION SQUASHING:")
        if det_gold_mean > det_nongold_mean and final_gold_mean < final_nongold_mean:
            print("   ⚠️ LIKELY ISSUE: Gold has higher det scores but lower final scores")
            print("   → Min-max normalization may be squashing gold advantage")
        else:
            print("   ✅ Not the primary issue")
        
        print()
        print("2. SEMANTIC DILUTION:")
        if sem_gold_mean < sem_nongold_mean:
            print("   ⚠️ LIKELY ISSUE: Non-gold chunks have HIGHER semantic scores")
            print("   → Semantic search is adding noise that hurts gold ranking")
            print(f"   → Gold sem mean: {sem_gold_mean:.4f}, Non-gold sem mean: {sem_nongold_mean:.4f}")
        else:
            print("   ✅ Semantic scores favor gold chunks")
        
        print()
        print("3. SCORE SCALE MISMATCH:")
        det_range = np.max(gold_det_all + nongold_det_all) - np.min(gold_det_all + nongold_det_all)
        sem_range = np.max(gold_sem_all + nongold_sem_all) - np.min(gold_sem_all + nongold_sem_all) if (gold_sem_all or nongold_sem_all) else 0
        print(f"   Det score range: {det_range:.4f}")
        print(f"   Sem score range: {sem_range:.4f}")
        if det_range > 10 * sem_range or sem_range > 10 * det_range:
            print("   ⚠️ Large scale difference - normalization critical")
        else:
            print("   ✅ Scales are comparable")
    
    print()
    print("4. MISSING ANCHOR BONUS:")
    anchor_gold = [a for a in all_low_ranked if a.is_anchor]
    non_anchor_gold = [a for a in all_low_ranked if not a.is_anchor]
    print(f"   Low-ranked gold with anchor: {len(anchor_gold)}")
    print(f"   Low-ranked gold without anchor: {len(non_anchor_gold)}")
    if non_anchor_gold:
        print("   ⚠️ Some gold chunks not getting anchor bonus")
    
    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"ranking_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_gold": total_gold,
            "found": total_found,
            "top_30": total_top_30,
            "ranked_30_plus": total_30_plus,
            "not_found": total_not_found,
        },
        "per_query_stats": all_stats,
        "low_ranked_gold": [
            {
                "query_id": a.query_id,
                "chunk_id": a.chunk_id,
                "rank": a.rank,
                "det_raw": a.det_score_raw,
                "sem_raw": a.sem_score_raw,
                "det_norm": a.det_score_normalized,
                "sem_norm": a.sem_score_normalized,
                "final": a.final_score,
                "found_by": a.found_by,
                "is_anchor": a.is_anchor,
                "terms_matched": a.terms_matched,
            }
            for a in all_low_ranked
        ],
        "score_distributions": {
            "gold_det_mean": float(np.mean(gold_det_all)) if gold_det_all else None,
            "gold_sem_mean": float(np.mean(gold_sem_all)) if gold_sem_all else None,
            "gold_final_mean": float(np.mean(gold_final_all)) if gold_final_all else None,
            "nongold_det_mean": float(np.mean(nongold_det_all)) if nongold_det_all else None,
            "nongold_sem_mean": float(np.mean(nongold_sem_all)) if nongold_sem_all else None,
            "nongold_final_mean": float(np.mean(nongold_final_all)) if nongold_final_all else None,
        },
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
