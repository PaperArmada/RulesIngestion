#!/usr/bin/env python3
"""
Anchor Term and Scoring Improvements Experiments.

Tests the new retrieval improvements:
1. Anchor term multiplier (priority weighting for original query terms)
2. Exact phrase matching (bonus for full phrase matches)
3. Match count penalty (diminishing returns for over-matching)
4. Anchor term bonus in reranking (separate bonus for anchor term coverage)

Run from RulesIngestion directory:
    uv run python run_anchor_term_experiments.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

# Load environment variables from parent .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env.development"
if env_path.exists():
    load_dotenv(env_path)
    print(f"📝 Loaded environment from: {env_path}")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from traversal import (
    TraversalIndex,
    HybridConfig,
    HybridRetriever,
    DEFAULT_EXPANSION_MODEL,
)


# Configuration
ENRICHED_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
GRAPH_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json")
EVAL_QUERIES_PATH = Path("blind_eval/batches/batch_001.json")
OUTPUT_DIR = Path("experiments/results")


@dataclass
class ExperimentResult:
    """Results from a single experiment run."""
    name: str
    config: Dict[str, Any]
    avg_recall_at_k: Dict[int, float]
    avg_latency_ms: float
    gold_found: int
    gold_total: int
    per_query_details: List[Dict[str, Any]]


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
    
    chunk_by_id = {chunk.get("id"): chunk for chunk in chunks}
    
    def semantic_search(query: str, k: int) -> List[Dict[str, Any]]:
        """Search using sentence embeddings."""
        query_embedding = model.encode([query])[0]
        
        similarities = chunk_embeddings @ query_embedding / (
            np.linalg.norm(chunk_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
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


def run_experiment(
    name: str,
    index: TraversalIndex,
    queries: List[Dict[str, Any]],
    config: HybridConfig,
) -> ExperimentResult:
    """Run a single experiment with the given configuration."""
    print(f"\n🧪 Running: {name}")
    print(f"   anchor_term_multiplier: {config.anchor_term_multiplier}")
    print(f"   anchor_term_bonus: {config.anchor_term_bonus}")
    print(f"   max_term_match_threshold: {config.max_term_match_threshold}")
    print(f"   use_idf: {config.use_idf}")
    
    retriever = HybridRetriever(index, config)
    
    recall_at_k_all: Dict[int, List[float]] = {1: [], 2: [], 5: [], 10: [], 20: [], 30: []}
    latencies = []
    total_gold_found = 0
    total_gold = 0
    per_query_details = []
    
    for query in queries:
        result = retriever.retrieve(
            query["query_text"],
            gold_chunk_ids=query["gold_chunk_ids"],
        )
        
        # Compute recall
        gold_ids = query["gold_chunk_ids"]
        total_gold += len(gold_ids)
        
        for k in recall_at_k_all.keys():
            top_k_ids = set(c.chunk_id for c in result.ranked_chunks[:k])
            hits = len(top_k_ids & gold_ids)
            recall = hits / max(1, len(gold_ids))
            recall_at_k_all[k].append(recall)
        
        # Count gold found
        all_result_ids = {c.chunk_id for c in result.ranked_chunks}
        gold_found = len(all_result_ids & gold_ids)
        total_gold_found += gold_found
        
        latencies.append(result.diagnostics.total_latency_ms)
        
        per_query_details.append({
            "query_id": query["query_id"],
            "gold_count": len(gold_ids),
            "gold_found": gold_found,
            "recall_at_10": recall_at_k_all[10][-1],
            "recall_at_30": recall_at_k_all[30][-1],
            "latency_ms": result.diagnostics.total_latency_ms,
        })
    
    # Compute averages
    avg_recall_at_k = {k: float(np.mean(v)) for k, v in recall_at_k_all.items()}
    avg_latency = float(np.mean(latencies))
    
    config_dict = {
        "anchor_term_multiplier": config.anchor_term_multiplier,
        "anchor_term_bonus": config.anchor_term_bonus,
        "max_term_match_threshold": config.max_term_match_threshold,
        "anchor_bonus": config.anchor_bonus,
        "term_coverage_bonus": config.term_coverage_bonus,
        "use_idf": config.use_idf,
    }
    
    return ExperimentResult(
        name=name,
        config=config_dict,
        avg_recall_at_k=avg_recall_at_k,
        avg_latency_ms=avg_latency,
        gold_found=total_gold_found,
        gold_total=total_gold,
        per_query_details=per_query_details,
    )


def main():
    print("=" * 70)
    print("🚀 ANCHOR TERM & SCORING IMPROVEMENTS EXPERIMENTS")
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
    print(f"   Bigrams: {len(index.bigram_to_chunks)}")
    print()
    
    # Create semantic search function
    semantic_search_fn = create_semantic_search_fn(chunks, index)
    
    # Define experiment configurations
    experiments = []
    
    # 1. Baseline (old defaults, no new features)
    experiments.append({
        "name": "Baseline (old defaults)",
        "config": HybridConfig(
            expansion_model=DEFAULT_EXPANSION_MODEL,
            deterministic_weight=0.5,
            semantic_weight=0.5,
            anchor_bonus=1.0,
            term_coverage_bonus=0.1,
            anchor_term_bonus=0.0,  # Disabled
            anchor_term_multiplier=1.0,  # No multiplier
            max_term_match_threshold=100,  # Effectively disabled
            top_k=100,
            enable_semantic=True,
            semantic_search_fn=semantic_search_fn,
            use_idf=True,
        ),
    })
    
    # 2. With anchor term multiplier only
    experiments.append({
        "name": "+ Anchor Term Multiplier (2.0x)",
        "config": HybridConfig(
            expansion_model=DEFAULT_EXPANSION_MODEL,
            deterministic_weight=0.5,
            semantic_weight=0.5,
            anchor_bonus=1.0,
            term_coverage_bonus=0.1,
            anchor_term_bonus=0.0,  # Disabled
            anchor_term_multiplier=2.0,  # NEW
            max_term_match_threshold=100,  # Disabled
            top_k=100,
            enable_semantic=True,
            semantic_search_fn=semantic_search_fn,
            use_idf=True,
        ),
    })
    
    # 3. With match count penalty only
    experiments.append({
        "name": "+ Match Count Penalty (threshold=6)",
        "config": HybridConfig(
            expansion_model=DEFAULT_EXPANSION_MODEL,
            deterministic_weight=0.5,
            semantic_weight=0.5,
            anchor_bonus=1.0,
            term_coverage_bonus=0.1,
            anchor_term_bonus=0.0,  # Disabled
            anchor_term_multiplier=1.0,  # Disabled
            max_term_match_threshold=6,  # NEW
            top_k=100,
            enable_semantic=True,
            semantic_search_fn=semantic_search_fn,
            use_idf=True,
        ),
    })
    
    # 4. With anchor term bonus in reranker only
    experiments.append({
        "name": "+ Anchor Term Bonus (0.3)",
        "config": HybridConfig(
            expansion_model=DEFAULT_EXPANSION_MODEL,
            deterministic_weight=0.5,
            semantic_weight=0.5,
            anchor_bonus=1.0,
            term_coverage_bonus=0.1,
            anchor_term_bonus=0.3,  # NEW
            anchor_term_multiplier=1.0,  # Disabled
            max_term_match_threshold=100,  # Disabled
            top_k=100,
            enable_semantic=True,
            semantic_search_fn=semantic_search_fn,
            use_idf=True,
        ),
    })
    
    # 5. All improvements combined
    experiments.append({
        "name": "ALL IMPROVEMENTS",
        "config": HybridConfig(
            expansion_model=DEFAULT_EXPANSION_MODEL,
            deterministic_weight=0.5,
            semantic_weight=0.5,
            anchor_bonus=1.0,
            term_coverage_bonus=0.1,
            anchor_term_bonus=0.3,  # NEW
            anchor_term_multiplier=2.0,  # NEW
            max_term_match_threshold=6,  # NEW
            top_k=100,
            enable_semantic=True,
            semantic_search_fn=semantic_search_fn,
            use_idf=True,
        ),
    })
    
    # Run all experiments
    results: List[ExperimentResult] = []
    
    for exp in experiments:
        result = run_experiment(
            name=exp["name"],
            index=index,
            queries=queries,
            config=exp["config"],
        )
        results.append(result)
        
        print(f"   R@10: {result.avg_recall_at_k[10]:.1%}, R@30: {result.avg_recall_at_k[30]:.1%}")
        print(f"   Gold found: {result.gold_found}/{result.gold_total}")
        print(f"   Avg latency: {result.avg_latency_ms:.0f}ms")
    
    # Summary table
    print()
    print("=" * 90)
    print("📊 EXPERIMENT SUMMARY")
    print("=" * 90)
    print(f"{'Experiment':<35} {'R@5':>8} {'R@10':>8} {'R@30':>8} {'Gold':>10} {'Latency':>10}")
    print("-" * 90)
    
    for result in results:
        r5 = f"{result.avg_recall_at_k[5]:.1%}"
        r10 = f"{result.avg_recall_at_k[10]:.1%}"
        r30 = f"{result.avg_recall_at_k[30]:.1%}"
        gold = f"{result.gold_found}/{result.gold_total}"
        lat = f"{result.avg_latency_ms:.0f}ms"
        print(f"{result.name:<35} {r5:>8} {r10:>8} {r30:>8} {gold:>10} {lat:>10}")
    
    print("-" * 90)
    
    # Compute improvement from baseline
    baseline = results[0]
    best = results[-1]  # ALL IMPROVEMENTS
    
    r10_improvement = best.avg_recall_at_k[10] - baseline.avg_recall_at_k[10]
    r30_improvement = best.avg_recall_at_k[30] - baseline.avg_recall_at_k[30]
    gold_improvement = best.gold_found - baseline.gold_found
    
    print()
    print("📈 IMPROVEMENT FROM BASELINE (ALL IMPROVEMENTS):")
    print(f"   R@10: {baseline.avg_recall_at_k[10]:.1%} → {best.avg_recall_at_k[10]:.1%} ({r10_improvement:+.1%})")
    print(f"   R@30: {baseline.avg_recall_at_k[30]:.1%} → {best.avg_recall_at_k[30]:.1%} ({r30_improvement:+.1%})")
    print(f"   Gold found: {baseline.gold_found} → {best.gold_found} ({gold_improvement:+d})")
    
    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"anchor_term_experiments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    results_json = {
        "timestamp": datetime.now().isoformat(),
        "experiments": [
            {
                "name": r.name,
                "config": r.config,
                "avg_recall_at_k": {str(k): v for k, v in r.avg_recall_at_k.items()},
                "avg_latency_ms": r.avg_latency_ms,
                "gold_found": r.gold_found,
                "gold_total": r.gold_total,
                "per_query_details": r.per_query_details,
            }
            for r in results
        ],
        "summary": {
            "baseline_r10": baseline.avg_recall_at_k[10],
            "best_r10": best.avg_recall_at_k[10],
            "r10_improvement": r10_improvement,
            "baseline_r30": baseline.avg_recall_at_k[30],
            "best_r30": best.avg_recall_at_k[30],
            "r30_improvement": r30_improvement,
        },
    }
    
    with open(output_file, "w") as f:
        json.dump(results_json, f, indent=2)
    
    print(f"\n📁 Results saved to: {output_file}")
    
    print()
    print("=" * 90)
    print("✅ ALL EXPERIMENTS COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
