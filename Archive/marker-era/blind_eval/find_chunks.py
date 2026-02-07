#!/usr/bin/env python3
"""
Find chunks on a specific page to help identify gold chunk IDs.

Usage:
    uv run python blind_eval/find_chunks.py --page 142 --enriched path/to/merged.enriched.json
    uv run python blind_eval/find_chunks.py --page 142 --search "grabbed"
"""

import argparse
import json
from pathlib import Path
from typing import Any


def load_chunks(enriched_path: Path) -> list[dict[str, Any]]:
    """Load enriched chunks from JSON file."""
    with open(enriched_path) as f:
        data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "chunks" in data:
        return data["chunks"]
    else:
        raise ValueError(f"Unknown format in {enriched_path}")


def find_chunks_on_page(
    chunks: list[dict[str, Any]],
    page: int,
) -> list[dict[str, Any]]:
    """Find all chunks from a specific page."""
    return [c for c in chunks if c.get("page") == page]


def find_chunks_by_text(
    chunks: list[dict[str, Any]],
    search_term: str,
    page: int | None = None,
) -> list[dict[str, Any]]:
    """Find chunks containing search term."""
    search_lower = search_term.lower()
    results = []
    
    for c in chunks:
        if page is not None and c.get("page") != page:
            continue
        
        text = c.get("text", "").lower()
        if search_lower in text:
            results.append(c)
    
    return results


def format_chunk(chunk: dict[str, Any], verbose: bool = False) -> str:
    """Format chunk for display."""
    chunk_id = chunk.get("id", "unknown")
    page = chunk.get("page", "?")
    content_kind = chunk.get("content_kind", "unknown")
    section_path = " > ".join(chunk.get("section_path", []))
    text = chunk.get("text", "")[:200]
    
    lines = [
        f"\n{'='*60}",
        f"ID: {chunk_id}",
        f"Page: {page} | Kind: {content_kind}",
        f"Section: {section_path}",
        f"Text preview:",
        f"  {text}...",
    ]
    
    if verbose:
        tags = chunk.get("tags", [])
        traits = chunk.get("traits", [])
        if tags:
            lines.append(f"Tags: {tags}")
        if traits:
            lines.append(f"Traits: {traits}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Find chunks for blind eval")
    parser.add_argument("--page", type=int, help="Page number to search")
    parser.add_argument("--search", type=str, help="Text to search for")
    parser.add_argument(
        "--enriched",
        type=Path,
        default=Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_19-16-02/enriched/merged.enriched.json"),
        help="Path to enriched chunks JSON",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more details")
    parser.add_argument("--limit", type=int, default=20, help="Max results to show")
    
    args = parser.parse_args()
    
    if not args.page and not args.search:
        parser.error("Must specify --page or --search")
    
    # Try to find the enriched file
    enriched_path = args.enriched
    if not enriched_path.exists():
        # Try common locations
        alternatives = [
            Path("Rules/StarFinder2e/PlayerCore/outputs/runs/2026-01-25_13-30-10/enriched/merged.enriched.json"),
            Path("Rules/StarFinder2e/PlayerCore/outputs/enriched/merged.enriched.json"),
        ]
        for alt in alternatives:
            if alt.exists():
                enriched_path = alt
                break
    
    if not enriched_path.exists():
        print(f"Error: Could not find enriched file at {enriched_path}")
        print("Specify path with --enriched")
        return
    
    print(f"Loading chunks from: {enriched_path}")
    chunks = load_chunks(enriched_path)
    print(f"Loaded {len(chunks)} chunks")
    
    results = []
    
    if args.page:
        results = find_chunks_on_page(chunks, args.page)
        print(f"\nFound {len(results)} chunks on page {args.page}")
    
    if args.search:
        results = find_chunks_by_text(chunks, args.search, args.page)
        print(f"\nFound {len(results)} chunks matching '{args.search}'")
    
    # Display results
    for chunk in results[:args.limit]:
        print(format_chunk(chunk, args.verbose))
    
    if len(results) > args.limit:
        print(f"\n... and {len(results) - args.limit} more results")
    
    # Print IDs for easy copy-paste
    if results:
        print(f"\n{'='*60}")
        print("Chunk IDs (copy-paste for blind_eval JSON):")
        for chunk in results[:args.limit]:
            print(f'  "{chunk.get("id", "unknown")}",')


if __name__ == "__main__":
    main()
