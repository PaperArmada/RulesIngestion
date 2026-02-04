"""
Core BFS graph traversal function.

Traversal is NOT ranking. Traversal only includes or excludes nodes.
Given a start set of nodes and a policy, compute a restricted candidate set.
"""

from __future__ import annotations

from collections import deque
from typing import Set

from .index import TraversalIndex
from .policy import TraversalPolicy, TraversalBudget


def traverse(
    index: TraversalIndex,
    start_nodes: Set[str],
    policy: TraversalPolicy,
    budget: TraversalBudget | None = None,
) -> Set[str]:
    """
    BFS traversal returning candidate node IDs.
    
    Traversal is a function:
        (graph, start_nodes, policy, budget) → Set[NodeID]
    
    It does NOT rank. It does NOT embed. It does NOT interpret.
    It only includes or excludes nodes.
    
    Args:
        index: TraversalIndex with adjacency and edge types
        start_nodes: Set of seed node IDs to start from
        policy: TraversalPolicy controlling which edges to follow
        budget: TraversalBudget with max_nodes and max_depth limits
        
    Returns:
        Set of candidate node IDs
    """
    if budget is None:
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
    
    # Ensure budget depth doesn't exceed policy depth
    max_depth = min(budget.max_depth, policy.max_depth)
    max_nodes = min(budget.max_nodes, policy.chunk_limit) if policy.chunk_limit else budget.max_nodes
    
    # Initialize visited set with start nodes
    visited: Set[str] = set(start_nodes)
    
    # BFS queue: (node_id, depth)
    frontier = deque((node, 0) for node in start_nodes)
    
    while frontier:
        node, depth = frontier.popleft()
        
        # Stop expanding if we've reached max depth
        if depth >= max_depth:
            continue
        
        # Get neighbors filtered by allowed edge types
        neighbors = index.get_neighbors(node, policy.allow_edges)
        
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
            
            # Stop if we've hit the node budget
            if len(visited) >= max_nodes:
                return visited
    
    return visited


def traverse_with_diagnostics(
    index: TraversalIndex,
    start_nodes: Set[str],
    policy: TraversalPolicy,
    budget: TraversalBudget | None = None,
) -> dict:
    """
    BFS traversal with diagnostic information.
    
    Returns a dict with:
        - candidates: Set of candidate node IDs
        - per_depth: Dict[int, int] - count of nodes found at each depth
        - edges_followed: Dict[str, int] - count of edges followed by type
        - budget_exhausted: bool - whether we hit the node limit
    """
    if budget is None:
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
    
    max_depth = min(budget.max_depth, policy.max_depth)
    max_nodes = min(budget.max_nodes, policy.chunk_limit) if policy.chunk_limit else budget.max_nodes
    
    visited: Set[str] = set(start_nodes)
    frontier = deque((node, 0) for node in start_nodes)
    
    per_depth: dict[int, int] = {0: len(start_nodes)}
    edges_followed: dict[str, int] = {}
    budget_exhausted = False
    
    while frontier:
        node, depth = frontier.popleft()
        
        if depth >= max_depth:
            continue
        
        neighbors = index.get_neighbors(node, policy.allow_edges)
        
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
            
            # Track per-depth counts
            new_depth = depth + 1
            per_depth[new_depth] = per_depth.get(new_depth, 0) + 1
            
            # Track edge types followed
            edge_type = index.edge_types.get((node, neighbor), "unknown")
            edges_followed[edge_type] = edges_followed.get(edge_type, 0) + 1
            
            if len(visited) >= max_nodes:
                budget_exhausted = True
                break
        
        if budget_exhausted:
            break
    
    return {
        "candidates": visited,
        "per_depth": per_depth,
        "edges_followed": edges_followed,
        "budget_exhausted": budget_exhausted,
        "total_visited": len(visited),
    }


def traverse_with_ranks(
    index: TraversalIndex,
    start_nodes: Set[str],
    policy: TraversalPolicy,
    budget: TraversalBudget | None = None,
) -> dict:
    """
    BFS traversal returning chunk IDs with their depth-based ranks.
    
    Chunks are ranked by BFS depth from anchor nodes:
    - Anchors (depth 0) get rank 1
    - Depth 1 chunks get next ranks
    - etc.
    
    Within each depth, chunks are ordered by their ID for determinism.
    
    Returns:
        Dict with:
        - ranked_chunks: List[Tuple[str, int, int]] - (chunk_id, depth, rank)
        - chunk_ranks: Dict[str, int] - chunk_id to rank mapping
        - depth_to_chunks: Dict[int, List[str]] - depth to list of chunk_ids
        - total_chunks: int
    """
    if budget is None:
        budget = TraversalBudget(
            max_nodes=policy.chunk_limit or 2000,
            max_depth=policy.max_depth,
        )
    
    max_depth = min(budget.max_depth, policy.max_depth)
    max_nodes = min(budget.max_nodes, policy.chunk_limit) if policy.chunk_limit else budget.max_nodes
    
    visited: Set[str] = set(start_nodes)
    frontier = deque((node, 0) for node in start_nodes)
    depth_to_chunks: dict[int, list[str]] = {0: sorted(start_nodes)}
    chunk_depths: dict[str, int] = {node: 0 for node in start_nodes}
    
    while frontier:
        node, depth = frontier.popleft()
        
        if depth >= max_depth:
            continue
        
        neighbors = index.get_neighbors(node, policy.allow_edges)
        
        for neighbor in neighbors:
            if neighbor in visited:
                continue
            
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
            
            # Track depth
            new_depth = depth + 1
            chunk_depths[neighbor] = new_depth
            if new_depth not in depth_to_chunks:
                depth_to_chunks[new_depth] = []
            depth_to_chunks[new_depth].append(neighbor)
            
            if len(visited) >= max_nodes:
                break
        
        if len(visited) >= max_nodes:
            break
    
    # Sort chunks within each depth for determinism
    for d in depth_to_chunks:
        depth_to_chunks[d].sort()
    
    # Assign ranks based on depth (closer = better rank)
    ranked_chunks = []
    chunk_ranks = {}
    rank = 1
    
    for depth in sorted(depth_to_chunks.keys()):
        for chunk_id in depth_to_chunks[depth]:
            ranked_chunks.append((chunk_id, depth, rank))
            chunk_ranks[chunk_id] = rank
            rank += 1
    
    return {
        "ranked_chunks": ranked_chunks,
        "chunk_ranks": chunk_ranks,
        "depth_to_chunks": depth_to_chunks,
        "total_chunks": len(visited),
        "candidates": visited,  # For compatibility with existing code
    }


def expand_with_siblings(
    index: TraversalIndex,
    candidates: Set[str],
    max_siblings: int = 20,
) -> Set[str]:
    """
    Expand candidate set to include section siblings.
    
    For each candidate, find other chunks in the same section_path
    and add them to the candidate set.
    """
    expanded = set(candidates)
    
    for chunk_id in list(candidates):
        chunk = index.chunk_by_id.get(chunk_id)
        if not chunk:
            continue
        
        section_path = chunk.get("section_path", [])
        if not section_path:
            continue
        
        # Find other chunks with the same section_path
        section_key = " > ".join(section_path).lower()
        if section_key in index.section_title_to_chunks:
            siblings = index.section_title_to_chunks[section_key]
            for sibling_id in list(siblings)[:max_siblings]:
                expanded.add(sibling_id)
    
    return expanded
