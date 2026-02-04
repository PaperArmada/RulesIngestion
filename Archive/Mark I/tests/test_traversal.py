"""
Tests for traversal-only retrieval system.

Test Categories:
1. Index Correctness - Verify index is built correctly
2. Anchor Finding - Query terms map to expected chunks
3. Intent Classification - Classifier matches pre-labeled intents
4. Traversal Reachability - Gold chunks are reachable via traversal
5. Candidate Set Size (Efficiency) - Traversal produces small candidate sets
6. End-to-End Recall Harness - High recall with small candidate sets
"""

import json
import pytest
from pathlib import Path
from typing import Dict, List, Set, Any

# Import traversal modules (to be implemented)
from traversal.index import TraversalIndex, tokenize_and_normalize
from traversal.seeds import find_anchor_nodes, select_documents
from traversal.intent import Intent, classify_intent, classify_intent_rules
from traversal.policy import TraversalPolicy, INTENT_POLICIES
from traversal.traverse import traverse, TraversalBudget
from traversal.retriever import retrieve_candidates, TraversalResult
from evaluation.benchmark.traversal_recall import (
    run_traversal_recall_harness,
    TraversalRecallResult,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def graph_data() -> Dict[str, Any]:
    """Load merged graph from PlayerCore outputs."""
    graph_path = Path(__file__).parent.parent / "Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.graph.json"
    if not graph_path.exists():
        pytest.skip(f"Graph file not found: {graph_path}")
    with open(graph_path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def chunks_data() -> List[Dict[str, Any]]:
    """Load merged enriched chunks from PlayerCore outputs."""
    chunks_path = Path(__file__).parent.parent / "Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"
    if not chunks_path.exists():
        pytest.skip(f"Chunks file not found: {chunks_path}")
    with open(chunks_path) as f:
        data = json.load(f)
        return data.get("chunks", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def index(graph_data, chunks_data) -> TraversalIndex:
    """Build traversal index from graph and chunks."""
    return TraversalIndex.build(graph_data, chunks_data)


@pytest.fixture(scope="module")
def golden_queries() -> List[Dict[str, Any]]:
    """Load golden benchmark queries with relevant_chunk_ids."""
    benchmark_path = Path(__file__).parent.parent / "Rules/StarFinder2e/Benchmark/starfinder_benchmark_dataset.json"
    if not benchmark_path.exists():
        pytest.skip(f"Benchmark file not found: {benchmark_path}")
    with open(benchmark_path) as f:
        data = json.load(f)
    # Filter to queries with relevant_chunk_ids
    return [
        {
            "id": f"q{i:03d}",
            "query_text": q["query"],
            "expected_chunk_ids": q.get("retrieval_review", {}).get("relevant_chunk_ids", []),
            "reference_answer": q.get("reference_answer", ""),
            "answer_characteristics": q.get("answer_characteristics", {}),
        }
        for i, q in enumerate(data)
        if q.get("retrieval_review", {}).get("relevant_chunk_ids")
    ]


# ============================================================================
# Test 1: Index Correctness
# ============================================================================

class TestIndexCorrectness:
    """Verify the index is built correctly from graph + chunks."""

    def test_index_has_chunks(self, index: TraversalIndex):
        """Index contains chunk data."""
        assert len(index.chunk_by_id) > 0, "Index should contain chunks"

    def test_index_has_adjacency(self, index: TraversalIndex):
        """Index contains graph adjacency."""
        assert len(index.adjacency) > 0, "Index should contain adjacency data"

    def test_index_term_coverage_sample(self, index: TraversalIndex, chunks_data: List[Dict]):
        """Sample of chunk text terms appear in term_to_chunks index."""
        # Check a sample of chunks (checking all would be slow)
        sample_chunks = chunks_data[:100]
        for chunk in sample_chunks:
            text = chunk.get("text", "")
            if not text or len(text) < 10:
                continue
            terms = tokenize_and_normalize(text)
            # At least some non-stopword terms should be indexed
            indexed_terms = [t for t in terms if t in index.term_to_chunks]
            assert len(indexed_terms) > 0 or len(terms) == 0, \
                f"No terms indexed for chunk {chunk.get('id')}"

    def test_index_tag_coverage(self, index: TraversalIndex, chunks_data: List[Dict]):
        """All chunk tags appear in tag_to_chunks index."""
        for chunk in chunks_data:
            for tag in chunk.get("tags", []):
                tag_lower = tag.lower()
                assert tag_lower in index.tag_to_chunks, \
                    f"Tag '{tag}' not in tag_to_chunks index"
                assert chunk["id"] in index.tag_to_chunks[tag_lower], \
                    f"Chunk {chunk['id']} not indexed under tag '{tag}'"

    def test_index_content_kind_coverage(self, index: TraversalIndex, chunks_data: List[Dict]):
        """All chunk content_kinds appear in content_kind_to_chunks index."""
        for chunk in chunks_data:
            kind = chunk.get("content_kind", "")
            if not kind:
                continue
            kind_lower = kind.lower()
            assert kind_lower in index.content_kind_to_chunks, \
                f"Content kind '{kind}' not in content_kind_to_chunks index"
            assert chunk["id"] in index.content_kind_to_chunks[kind_lower], \
                f"Chunk {chunk['id']} not indexed under content_kind '{kind}'"

    def test_index_adjacency_bidirectional(self, index: TraversalIndex):
        """Graph adjacency is bidirectional."""
        # Sample check - don't check all edges
        checked = 0
        for node, neighbors in list(index.adjacency.items())[:100]:
            for neighbor in list(neighbors)[:10]:
                if neighbor in index.adjacency:
                    assert node in index.adjacency[neighbor], \
                        f"Edge {node} -> {neighbor} not bidirectional"
                checked += 1
        assert checked > 0, "Should have checked some edges"


# ============================================================================
# Test 2: Anchor Finding
# ============================================================================

class TestAnchorFinding:
    """Verify query terms map to expected anchor nodes."""

    def test_anchor_finding_returns_set(self, index: TraversalIndex):
        """Anchor finding returns a set of node IDs."""
        anchors = find_anchor_nodes("What is a spell?", index)
        assert isinstance(anchors, set), "Anchors should be a set"

    def test_anchor_finding_nonempty_for_common_terms(self, index: TraversalIndex):
        """Common TTRPG terms should find anchors."""
        test_queries = [
            "What is a spell?",
            "How do I make an attack?",
            "What are the conditions?",
            "How does damage work?",
        ]
        for query in test_queries:
            anchors = find_anchor_nodes(query, index)
            assert len(anchors) > 0, f"No anchors found for query: {query}"

    def test_anchor_finding_from_golden_query(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Golden queries should find at least some anchors."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        queries_with_anchors = 0
        for query in golden_queries[:10]:  # Check first 10
            anchors = find_anchor_nodes(query["query_text"], index)
            if len(anchors) > 0:
                queries_with_anchors += 1
        
        # At least 50% of queries should find anchors
        assert queries_with_anchors >= 5, \
            f"Only {queries_with_anchors}/10 queries found anchors"


# ============================================================================
# Test 3: Intent Classification
# ============================================================================

class TestIntentClassification:
    """Verify intent classifier works correctly."""

    def test_intent_definition_patterns(self):
        """Definition queries are classified correctly."""
        definition_queries = [
            "What is flat-footed?",
            "What does stunned do?",
            "Define prone condition",
        ]
        for query in definition_queries:
            intent = classify_intent_rules(query)
            assert intent == Intent.DEFINITION or intent is None, \
                f"Expected DEFINITION for '{query}', got {intent}"

    def test_intent_procedure_patterns(self):
        """Procedure queries are classified correctly."""
        procedure_queries = [
            "How do I cast a spell?",
            "Steps for making an attack",
            "How to grapple an enemy",
        ]
        for query in procedure_queries:
            intent = classify_intent_rules(query)
            assert intent == Intent.PROCEDURE or intent is None, \
                f"Expected PROCEDURE for '{query}', got {intent}"

    def test_intent_lookup_patterns(self):
        """Lookup queries are classified correctly."""
        lookup_queries = [
            "What is the DC for athletics?",
            "Table of weapon damage",
            "List of conditions",
        ]
        for query in lookup_queries:
            intent = classify_intent_rules(query)
            assert intent == Intent.LOOKUP or intent is None, \
                f"Expected LOOKUP for '{query}', got {intent}"

    def test_classify_intent_returns_intent(self):
        """classify_intent always returns an Intent enum."""
        query = "What does flat-footed do?"
        intent = classify_intent(query)
        assert isinstance(intent, Intent), \
            f"Expected Intent enum, got {type(intent)}"


# ============================================================================
# Test 4: Traversal Reachability (Core Test)
# ============================================================================

class TestTraversalReachability:
    """Verify gold chunks are reachable via traversal from anchors."""

    def test_traverse_returns_set(self, index: TraversalIndex):
        """Traverse returns a set of node IDs."""
        start_nodes = set(list(index.chunk_by_id.keys())[:5])
        policy = INTENT_POLICIES[Intent.DEFINITION]
        budget = TraversalBudget(max_nodes=100, max_depth=2)
        
        candidates = traverse(index, start_nodes, policy, budget)
        assert isinstance(candidates, set), "Candidates should be a set"

    def test_traverse_includes_start_nodes(self, index: TraversalIndex):
        """Traverse result includes the start nodes."""
        start_nodes = set(list(index.chunk_by_id.keys())[:5])
        policy = INTENT_POLICIES[Intent.DEFINITION]
        budget = TraversalBudget(max_nodes=100, max_depth=2)
        
        candidates = traverse(index, start_nodes, policy, budget)
        for node in start_nodes:
            assert node in candidates, f"Start node {node} not in candidates"

    def test_traverse_respects_budget(self, index: TraversalIndex):
        """Traverse respects max_nodes budget."""
        start_nodes = set(list(index.chunk_by_id.keys())[:5])
        policy = INTENT_POLICIES[Intent.DEFINITION]
        budget = TraversalBudget(max_nodes=50, max_depth=10)
        
        candidates = traverse(index, start_nodes, policy, budget)
        assert len(candidates) <= budget.max_nodes, \
            f"Candidates {len(candidates)} exceeds budget {budget.max_nodes}"

    def test_golden_query_reachability(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Gold chunk is reachable for at least some golden queries."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        reachable_count = 0
        for query in golden_queries[:10]:
            anchors = find_anchor_nodes(query["query_text"], index)
            if not anchors:
                continue
            
            intent = classify_intent(query["query_text"])
            policy = INTENT_POLICIES[intent]
            budget = TraversalBudget(max_nodes=2000, max_depth=policy.max_depth)
            
            candidates = traverse(index, anchors, policy, budget)
            
            gold_ids = set(query["expected_chunk_ids"])
            if gold_ids & candidates:
                reachable_count += 1
        
        # At least 30% should be reachable (conservative for initial test)
        assert reachable_count >= 3, \
            f"Only {reachable_count}/10 queries had reachable gold chunks"


# ============================================================================
# Test 5: Candidate Set Size (Efficiency)
# ============================================================================

class TestCandidateSetEfficiency:
    """Verify traversal produces reasonably small candidate sets."""

    def test_candidate_set_not_entire_corpus(self, index: TraversalIndex):
        """Traversal should not return the entire corpus."""
        start_nodes = set(list(index.chunk_by_id.keys())[:5])
        policy = INTENT_POLICIES[Intent.DEFINITION]
        budget = TraversalBudget(max_nodes=500, max_depth=2)
        
        candidates = traverse(index, start_nodes, policy, budget)
        total_chunks = len(index.chunk_by_id)
        
        fraction = len(candidates) / total_chunks if total_chunks > 0 else 0
        assert fraction < 0.5, \
            f"Candidate fraction {fraction:.2%} is >= 50% (too permissive)"

    def test_candidate_fraction_golden_queries(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Average candidate set is reasonably sized for golden queries."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        total_chunks = len(index.chunk_by_id)
        fractions = []
        
        for query in golden_queries[:10]:
            anchors = find_anchor_nodes(query["query_text"], index)
            if not anchors:
                continue
            
            intent = classify_intent(query["query_text"])
            policy = INTENT_POLICIES[intent]
            budget = TraversalBudget(max_nodes=2000, max_depth=policy.max_depth)
            
            candidates = traverse(index, anchors, policy, budget)
            fraction = len(candidates) / total_chunks if total_chunks > 0 else 0
            fractions.append(fraction)
        
        if fractions:
            avg_fraction = sum(fractions) / len(fractions)
            # Allow up to 50% for initial tests, tighten later
            assert avg_fraction < 0.50, \
                f"Avg candidate fraction {avg_fraction:.2%} >= 50%"


# ============================================================================
# Test 6: End-to-End Recall Harness
# ============================================================================

class TestRecallHarness:
    """The main success metric - high recall with small candidate sets."""

    def test_recall_harness_runs(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Recall harness runs without error."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        results = run_traversal_recall_harness(golden_queries[:5], index)
        assert isinstance(results, TraversalRecallResult), \
            f"Expected TraversalRecallResult, got {type(results)}"

    def test_recall_harness_metrics_present(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Recall harness returns expected metrics."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        results = run_traversal_recall_harness(golden_queries[:5], index)
        
        assert hasattr(results, "total_queries"), "Missing total_queries"
        assert hasattr(results, "reachable_queries"), "Missing reachable_queries"
        assert hasattr(results, "recall"), "Missing recall"
        assert hasattr(results, "avg_candidate_fraction"), "Missing avg_candidate_fraction"

    def test_recall_target(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Traversal recall meets target (>= 90%)."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        results = run_traversal_recall_harness(golden_queries, index)
        
        # Target: 90% recall
        assert results.recall >= 0.90, \
            f"Recall {results.recall:.2%} < 90% target"

    def test_efficiency_target(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Candidate fraction meets target (< 25%)."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        results = run_traversal_recall_harness(golden_queries, index)
        
        # Target: < 25% of corpus
        assert results.avg_candidate_fraction < 0.25, \
            f"Avg candidate fraction {results.avg_candidate_fraction:.2%} >= 25% target"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_retrieve_candidates_returns_result(self, index: TraversalIndex, golden_queries: List[Dict]):
        """retrieve_candidates returns a TraversalResult."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        query = golden_queries[0]
        result = retrieve_candidates(query["query_text"], index)
        
        assert isinstance(result, TraversalResult), \
            f"Expected TraversalResult, got {type(result)}"
        assert hasattr(result, "candidate_ids"), "Missing candidate_ids"
        assert hasattr(result, "anchors"), "Missing anchors"
        assert hasattr(result, "intent"), "Missing intent"

    def test_full_pipeline_golden_query(self, index: TraversalIndex, golden_queries: List[Dict]):
        """Full pipeline processes a golden query."""
        if not golden_queries:
            pytest.skip("No golden queries available")
        
        query = golden_queries[0]
        result = retrieve_candidates(query["query_text"], index)
        
        # Check that candidates were found
        assert len(result.candidate_ids) > 0, "No candidates found"
        
        # Check if any gold chunk is in candidates
        gold_ids = set(query["expected_chunk_ids"])
        hits = gold_ids & result.candidate_ids
        
        # Log for debugging (not assertion, for initial runs)
        print(f"\nQuery: {query['query_text'][:50]}...")
        print(f"Anchors: {len(result.anchors)}")
        print(f"Intent: {result.intent}")
        print(f"Candidates: {len(result.candidate_ids)}")
        print(f"Gold hits: {len(hits)}/{len(gold_ids)}")
