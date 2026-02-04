"""
Blind evaluation tests.

These tests run on human-created, randomly-selected queries
that were created without knowledge of the traversal system's behavior.

Run with:
    uv run pytest tests/test_blind_eval.py -v
"""

import json
from pathlib import Path
from typing import Any

import pytest

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from traversal import TraversalIndex, retrieve_candidates, TraversalConfig, build_config


# ============================================================================
# Fixtures
# ============================================================================

GRAPH_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json")
ENRICHED_PATH = Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json")
BLIND_EVAL_DIR = Path(__file__).parent.parent / "blind_eval" / "batches"


@pytest.fixture(scope="module")
def traversal_data() -> tuple[dict, list]:
    """Load graph and chunks."""
    if not GRAPH_PATH.exists() or not ENRICHED_PATH.exists():
        pytest.skip("Graph/enriched files not found")
    
    with open(GRAPH_PATH) as f:
        graph = json.load(f)
    
    with open(ENRICHED_PATH) as f:
        chunks_data = json.load(f)
    
    if isinstance(chunks_data, list):
        chunks = chunks_data
    else:
        chunks = chunks_data.get("chunks", [])
    
    return graph, chunks


@pytest.fixture(scope="module")
def index(traversal_data) -> TraversalIndex:
    """Build traversal index."""
    graph, chunks = traversal_data
    return TraversalIndex.build(graph, chunks)


@pytest.fixture(scope="module")
def config(traversal_data) -> TraversalConfig:
    """Build traversal config."""
    _, chunks = traversal_data
    return build_config(chunks, ruleset_id="StarFinder2e")


def load_all_batches() -> list[dict[str, Any]]:
    """Load all blind eval batches."""
    batches = []
    
    if not BLIND_EVAL_DIR.exists():
        return batches
    
    for batch_file in sorted(BLIND_EVAL_DIR.glob("batch_*.json")):
        with open(batch_file) as f:
            batch = json.load(f)
        
        if batch.get("queries"):
            batches.append(batch)
    
    return batches


def get_all_queries() -> list[tuple[str, dict]]:
    """Get all queries from all batches for parametrization."""
    queries = []
    
    for batch in load_all_batches():
        batch_id = batch["metadata"]["batch_id"]
        for query in batch["queries"]:
            queries.append((f"batch_{batch_id}_{query['id']}", query))
    
    return queries


# ============================================================================
# Tests
# ============================================================================

class TestBlindEvalBatches:
    """Test blind evaluation batches."""
    
    def test_batch_files_exist(self):
        """Verify batch directory exists."""
        assert BLIND_EVAL_DIR.exists(), f"Blind eval directory not found: {BLIND_EVAL_DIR}"
    
    def test_batch_format_valid(self):
        """Verify batch files have valid format."""
        for batch_file in BLIND_EVAL_DIR.glob("batch_*.json"):
            with open(batch_file) as f:
                batch = json.load(f)
            
            assert "metadata" in batch, f"Missing metadata in {batch_file.name}"
            assert "queries" in batch, f"Missing queries in {batch_file.name}"
            assert "batch_id" in batch["metadata"], f"Missing batch_id in {batch_file.name}"
            
            for query in batch["queries"]:
                assert "id" in query, f"Missing id in query: {batch_file.name}"
                assert "question" in query, f"Missing question in query: {batch_file.name}"
                assert "gold_chunk_ids" in query, f"Missing gold_chunk_ids in query: {batch_file.name}"


class TestBlindEvalRecall:
    """Test recall on blind evaluation queries."""
    
    @pytest.fixture(autouse=True)
    def setup(self, index, config):
        """Store fixtures for use in tests."""
        self.index = index
        self.config = config
    
    def test_blind_eval_has_queries(self):
        """Verify we have blind eval queries to test."""
        queries = get_all_queries()
        # This is expected to be empty initially - will be populated by user
        # We don't fail if empty, just skip
        if not queries:
            pytest.skip("No blind eval queries yet - add queries to batches/")
    
    @pytest.mark.parametrize("query_id,query", get_all_queries() or [("skip", {})])
    def test_query_recall(self, query_id: str, query: dict, index, config):
        """Test that each blind eval query retrieves its gold chunk."""
        if query_id == "skip":
            pytest.skip("No blind eval queries yet")
        
        question = query["question"]
        gold_ids = query["gold_chunk_ids"]
        
        # Run traversal
        result = retrieve_candidates(question, index, config=config)
        
        # Check if any gold chunk was retrieved
        retrieved = result.candidate_ids
        matched = [gid for gid in gold_ids if gid in retrieved]
        
        assert matched, (
            f"No gold chunks retrieved for query: {question[:50]}...\n"
            f"Gold IDs: {gold_ids}\n"
            f"Retrieved: {len(retrieved)} candidates\n"
            f"Intent: {result.intent.name}\n"
            f"Anchors: {len(result.anchors)}"
        )


class TestBlindEvalSummary:
    """Summary metrics for blind evaluation."""
    
    def test_overall_recall_target(self, index, config):
        """Test that overall blind eval recall meets target."""
        queries = get_all_queries()
        
        if not queries:
            pytest.skip("No blind eval queries yet")
        
        hits = 0
        for query_id, query in queries:
            question = query["question"]
            gold_ids = query["gold_chunk_ids"]
            
            result = retrieve_candidates(question, index, config=config)
            
            if any(gid in result.candidate_ids for gid in gold_ids):
                hits += 1
        
        recall = hits / len(queries) if queries else 0.0
        
        # Target: 85% recall on blind eval
        # This is lower than the 90% target for curated benchmarks
        # because blind eval is intentionally harder
        assert recall >= 0.85, (
            f"Blind eval recall {recall:.2%} below 85% target\n"
            f"Hits: {hits}/{len(queries)}"
        )
    
    def test_print_summary(self, index, config):
        """Print summary of blind eval results (always passes, for reporting)."""
        queries = get_all_queries()
        
        if not queries:
            print("\nNo blind eval queries yet - add queries to batches/")
            return
        
        hits = 0
        total_candidates = 0
        failures = []
        
        for query_id, query in queries:
            question = query["question"]
            gold_ids = query["gold_chunk_ids"]
            
            result = retrieve_candidates(question, index, config=config)
            total_candidates += len(result.candidate_ids)
            
            if any(gid in result.candidate_ids for gid in gold_ids):
                hits += 1
            else:
                failures.append((query_id, question[:50]))
        
        recall = hits / len(queries) if queries else 0.0
        avg_candidates = total_candidates / len(queries) if queries else 0.0
        
        print(f"\n{'='*50}")
        print(f"BLIND EVAL SUMMARY")
        print(f"{'='*50}")
        print(f"Total queries: {len(queries)}")
        print(f"Hits: {hits}")
        print(f"Recall: {recall:.2%}")
        print(f"Avg candidates: {avg_candidates:.1f}")
        
        if failures:
            print(f"\nFailures ({len(failures)}):")
            for qid, q in failures:
                print(f"  ❌ {qid}: {q}...")
