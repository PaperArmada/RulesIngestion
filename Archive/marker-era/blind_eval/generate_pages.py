#!/usr/bin/env python3
"""
Generate random page numbers for blind evaluation.

Usage:
    uv run python blind_eval/generate_pages.py --count 10
    uv run python blind_eval/generate_pages.py --count 10 --pdf path/to/pdf.pdf
"""

import argparse
import random
from pathlib import Path

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


def get_page_count(pdf_path: Path) -> int:
    """Get total page count from PDF."""
    if not HAS_FITZ:
        raise RuntimeError("PyMuPDF (fitz) required. Install with: uv add pymupdf")
    
    doc = fitz.open(str(pdf_path))
    count = doc.page_count
    doc.close()
    return count


def generate_random_pages(
    count: int,
    total_pages: int = 320,
    exclude_pages: set[int] | None = None,
) -> list[int]:
    """
    Generate random page numbers.
    
    Args:
        count: Number of pages to select
        total_pages: Total pages in document
        exclude_pages: Pages to exclude (e.g., table of contents, index)
        
    Returns:
        List of random page numbers (1-indexed)
    """
    exclude = exclude_pages or set()
    
    # Exclude common non-content pages
    default_exclude = {
        1, 2, 3, 4,  # Front matter
        total_pages, total_pages - 1,  # Back matter
    }
    exclude = exclude | default_exclude
    
    available = [p for p in range(1, total_pages + 1) if p not in exclude]
    
    if count > len(available):
        raise ValueError(f"Cannot select {count} pages from {len(available)} available")
    
    return sorted(random.sample(available, count))


def main():
    parser = argparse.ArgumentParser(description="Generate random pages for blind eval")
    parser.add_argument("--count", type=int, default=10, help="Number of pages to generate")
    parser.add_argument("--total", type=int, default=320, help="Total pages in document")
    parser.add_argument("--pdf", type=Path, help="PDF file to get page count from")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument("--exclude", type=str, help="Comma-separated pages to exclude")
    
    args = parser.parse_args()
    
    if args.seed:
        random.seed(args.seed)
    
    total_pages = args.total
    if args.pdf and args.pdf.exists():
        total_pages = get_page_count(args.pdf)
        print(f"PDF has {total_pages} pages")
    
    exclude = set()
    if args.exclude:
        exclude = {int(p.strip()) for p in args.exclude.split(",")}
    
    pages = generate_random_pages(args.count, total_pages, exclude)
    
    print(f"\n{'='*50}")
    print(f"BLIND EVAL: {args.count} random pages selected")
    print(f"{'='*50}")
    print(f"\nPages to evaluate: {pages}")
    print(f"\nInstructions:")
    print(f"  1. Open the PDF")
    print(f"  2. Navigate to each page")
    print(f"  3. Write a natural question about the content")
    print(f"  4. Find the gold chunk ID using find_chunks.py")
    print(f"  5. Add to batches/batch_NNN.json")
    print(f"\nPage list (copy-paste friendly):")
    for i, page in enumerate(pages, 1):
        print(f"  {i}. Page {page}")


if __name__ == "__main__":
    main()
