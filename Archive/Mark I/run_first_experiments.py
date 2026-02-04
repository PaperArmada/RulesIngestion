#!/usr/bin/env python3
"""
First experiments with the hybrid retrieval system.

Experiments:
1. Baseline: gpt-5.2 with deterministic search only
2. Model Comparison: gpt-5.2 vs gpt-4o-mini

Run from RulesIngestion directory:
    uv run python run_first_experiments.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

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
    EXPANSION_MODELS,
)
from experiments import (
    ExperimentRunner,
    ExperimentQuery,
    load_queries_from_json,
    print_run_summary,
    print_grid_search_summary,
)


# Configuration
ENRICHED_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
GRAPH_DATA_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json")
EVAL_QUERIES_PATH = Path("blind_eval/batches/batch_001.json")
OUTPUT_DIR = Path("experiments/results")


def load_enriched_chunks(path: Path) -> list:
    """Load enriched chunks from JSON file."""
    print(f"📂 Loading enriched data from: {path}")
    with open(path) as f:
        data = json.load(f)
    
    # Handle different formats
    if isinstance(data, list):
        chunks = data
    elif isinstance(data, dict) and "chunks" in data:
        chunks = data["chunks"]
    else:
        # Assume it's a dict with chunk IDs as keys
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


def filter_complete_queries(queries: list) -> list:
    """Filter out incomplete (TODO) queries."""
    complete = []
    for q in queries:
        # Skip queries with TODO in question or gold_chunk_ids
        if "TODO" in q.query_text or any("TODO" in g for g in q.gold_chunk_ids):
            print(f"   ⏭️  Skipping incomplete: {q.query_id}")
            continue
        complete.append(q)
    return complete


def run_baseline_experiment(runner: ExperimentRunner) -> None:
    """Experiment 1: Baseline with gpt-5.2 (deterministic only, NO IDF)."""
    print("\n" + "="*70)
    print("🧪 EXPERIMENT 1: Baseline with gpt-5.2 (NO IDF weighting)")
    print("="*70)
    
    config = HybridConfig(
        expansion_model=DEFAULT_EXPANSION_MODEL,  # gpt-5.2
        deterministic_weight=1.0,
        semantic_weight=0.0,  # No semantic search
        expansion_terms=7,
        top_k=30,
        use_idf=False,  # Baseline: no IDF weighting
    )
    
    print(f"   Model: {config.expansion_model or DEFAULT_EXPANSION_MODEL}")
    print(f"   Expansion terms: {config.expansion_terms}")
    print(f"   Weights: det={config.deterministic_weight}, sem={config.semantic_weight}")
    print(f"   IDF weighting: {config.use_idf}")
    print()
    
    run = runner.run_single(config, save_results=True, save_per_query=True)
    print_run_summary(run)
    
    # Print per-query details
    if run.per_query_results:
        print("\n📊 Per-Query Results:")
        print("-"*70)
        for pq in run.per_query_results:
            r1 = pq["recall_at_k"].get(1, 0)
            r5 = pq["recall_at_k"].get(5, 0)
            r10 = pq["recall_at_k"].get(10, 0)
            print(f"  {pq['query_id']}: R@1={r1:.0%}, R@5={r5:.0%}, R@10={r10:.0%}")
            print(f"    Query: {pq['query_text'][:60]}...")
            print(f"    Gold chunks: {pq['gold_count']}, Latency: {pq['latency_ms']:.0f}ms")
            print(f"    Expanded terms: {pq['expanded_terms'][:5]}...")
            print()
    
    return run


def run_idf_experiment(runner: ExperimentRunner) -> None:
    """Experiment 1b: With IDF weighting (rare terms score higher)."""
    print("\n" + "="*70)
    print("🧪 EXPERIMENT 1b: With IDF Weighting + Bigram Bonus")
    print("="*70)
    
    config = HybridConfig(
        expansion_model=DEFAULT_EXPANSION_MODEL,  # gpt-5.2
        deterministic_weight=1.0,
        semantic_weight=0.0,  # No semantic search
        expansion_terms=7,
        top_k=30,
        use_idf=True,  # NEW: IDF weighting enabled
    )
    
    print(f"   Model: {config.expansion_model or DEFAULT_EXPANSION_MODEL}")
    print(f"   Expansion terms: {config.expansion_terms}")
    print(f"   Weights: det={config.deterministic_weight}, sem={config.semantic_weight}")
    print(f"   IDF weighting: {config.use_idf}")
    print()
    
    run = runner.run_single(config, save_results=True, save_per_query=True)
    print_run_summary(run)
    
    # Print per-query details
    if run.per_query_results:
        print("\n📊 Per-Query Results:")
        print("-"*70)
        for pq in run.per_query_results:
            r1 = pq["recall_at_k"].get(1, 0)
            r5 = pq["recall_at_k"].get(5, 0)
            r10 = pq["recall_at_k"].get(10, 0)
            print(f"  {pq['query_id']}: R@1={r1:.0%}, R@5={r5:.0%}, R@10={r10:.0%}")
            print(f"    Query: {pq['query_text'][:60]}...")
            print(f"    Gold chunks: {pq['gold_count']}, Latency: {pq['latency_ms']:.0f}ms")
            print(f"    Expanded terms: {pq['expanded_terms'][:5]}...")
            print()
    
    return run


def run_model_comparison(runner: ExperimentRunner) -> None:
    """Experiment 2: Compare available expansion models."""
    print("\n" + "="*70)
    print("🧪 EXPERIMENT 2: Model Comparison")
    print("="*70)
    
    # Only test gpt-5.2 for now (other models have parameter compatibility issues)
    models_to_test = ["gpt-5.2"]
    print(f"   Models to test: {models_to_test}")
    print("   Note: gpt-5-mini/nano skipped due to temperature parameter issues")
    
    runs = []
    for model_name in models_to_test:
        print(f"\n   Testing: {model_name}")
        
        config = HybridConfig(
            expansion_model=model_name,
            deterministic_weight=1.0,
            semantic_weight=0.0,
            expansion_terms=7,
            top_k=30,
        )
        
        run = runner.run_single(config, save_results=True, save_per_query=True)
        runs.append(run)
        print_run_summary(run)
    
    # Comparison summary
    print("\n" + "="*70)
    print("📊 Model Comparison Summary")
    print("="*70)
    print(f"{'Model':<15} {'R@1':>8} {'R@5':>8} {'R@10':>8} {'R@30':>8} {'Latency':>10}")
    print("-"*70)
    
    for run in runs:
        m = run.metrics
        model = run.config.expansion_model if run.config.expansion_model else DEFAULT_EXPANSION_MODEL
        r1 = f"{m.avg_recall_at_k.get(1, 0):.1%}"
        r5 = f"{m.avg_recall_at_k.get(5, 0):.1%}"
        r10 = f"{m.avg_recall_at_k.get(10, 0):.1%}"
        r30 = f"{m.avg_recall_at_k.get(30, 0):.1%}"
        lat = f"{m.avg_latency_ms:.0f}ms"
        print(f"{model:<15} {r1:>8} {r5:>8} {r10:>8} {r30:>8} {lat:>10}")
    
    print("="*70)
    
    return runs


def main():
    print("🚀 Starting First Experiments with Hybrid Retrieval")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print(f"   Default model: {DEFAULT_EXPANSION_MODEL}")
    print(f"   Available models: {list(EXPANSION_MODELS.keys())}")
    print()
    
    # Load enriched data and graph
    chunks = load_enriched_chunks(ENRICHED_DATA_PATH)
    graph = load_graph(GRAPH_DATA_PATH)
    
    # Build TraversalIndex
    print("🔨 Building TraversalIndex...")
    index = TraversalIndex.build(graph, chunks)
    print(f"   Index stats: {index.total_chunks} chunks, {index.total_edges} edges")
    print(f"   Term index: {len(index.term_to_chunks)} unique terms")
    print(f"   Section index: {len(index.section_title_to_chunks)} sections")
    print(f"   Content kinds: {len(index.content_kind_to_chunks)}")
    print()
    
    # Load evaluation queries
    print(f"📋 Loading evaluation queries from: {EVAL_QUERIES_PATH}")
    queries = load_queries_from_json(EVAL_QUERIES_PATH)
    print(f"   Loaded {len(queries)} queries")
    
    # Filter complete queries
    queries = filter_complete_queries(queries)
    print(f"   {len(queries)} complete queries for evaluation")
    print()
    
    if len(queries) == 0:
        print("❌ No complete queries found! Check batch_001.json")
        return
    
    # Create experiment runner
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = ExperimentRunner(
        index=index,
        queries=queries,
        semantic_search_fn=None,  # No semantic search yet
        output_dir=OUTPUT_DIR,
    )
    
    # Run experiments
    print("\n" + "="*70)
    print("Starting experiments...")
    print("="*70)
    
    # Experiment 1: Baseline (no IDF)
    baseline_run = run_baseline_experiment(runner)
    
    # Experiment 1b: With IDF weighting
    idf_run = run_idf_experiment(runner)
    
    # Comparison summary
    print("\n" + "="*70)
    print("📊 IDF WEIGHTING COMPARISON")
    print("="*70)
    print(f"{'Scoring':<20} {'R@1':>8} {'R@5':>8} {'R@10':>8} {'R@30':>8} {'Latency':>10}")
    print("-"*70)
    
    for run, label in [(baseline_run, "No IDF (baseline)"), (idf_run, "With IDF + Bigram")]:
        m = run.metrics
        r1 = f"{m.avg_recall_at_k.get(1, 0):.1%}"
        r5 = f"{m.avg_recall_at_k.get(5, 0):.1%}"
        r10 = f"{m.avg_recall_at_k.get(10, 0):.1%}"
        r30 = f"{m.avg_recall_at_k.get(30, 0):.1%}"
        lat = f"{m.avg_latency_ms:.0f}ms"
        print(f"{label:<20} {r1:>8} {r5:>8} {r10:>8} {r30:>8} {lat:>10}")
    
    print("="*70)
    
    # Show improvement
    baseline_r10 = baseline_run.metrics.avg_recall_at_k.get(10, 0)
    idf_r10 = idf_run.metrics.avg_recall_at_k.get(10, 0)
    improvement = idf_r10 - baseline_r10
    print(f"\n📈 Recall@10 improvement: {baseline_r10:.1%} → {idf_r10:.1%} ({improvement:+.1%})")
    
    baseline_r30 = baseline_run.metrics.avg_recall_at_k.get(30, 0)
    idf_r30 = idf_run.metrics.avg_recall_at_k.get(30, 0)
    improvement30 = idf_r30 - baseline_r30
    print(f"📈 Recall@30 improvement: {baseline_r30:.1%} → {idf_r30:.1%} ({improvement30:+.1%})")
    
    # Final summary
    print("\n" + "="*70)
    print("✅ ALL EXPERIMENTS COMPLETE")
    print("="*70)
    print(f"Results saved to: {OUTPUT_DIR}")
    print()


if __name__ == "__main__":
    main()
