"""CLI for building a corpus self-portrait.

Usage:
  uv run python -m tinker.scripts.build_self_portrait \\
      --substrate-dir out/swcr --document-id Swords_Wizardry \\
      --corpus-id swcr [--no-llm] [--no-llm-glossary]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tinker.introspect.build import build_self_portrait  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the corpus self-portrait.")
    parser.add_argument(
        "--substrate-dir",
        type=Path,
        required=True,
        help="Directory containing Stage B outputs (<stem>_p*/stageB.evidence_units.json).",
    )
    parser.add_argument(
        "--document-id",
        type=str,
        required=True,
        help="Document ID used by retrieval_lab.substrate_loader.load_evidence_units.",
    )
    parser.add_argument(
        "--corpus-id",
        type=str,
        default=None,
        help="Short corpus tag (used in output paths). Defaults to document-id.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for corpus_self_portrait.json. "
        "Defaults to out/tinker/<corpus-id>/corpus_self_portrait.json.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable all LLM calls (cluster labels become empty, glossary "
        "is regex-only).",
    )
    parser.add_argument(
        "--llm-glossary-max",
        type=int,
        default=50,
        help="Max units the glossary pass will send to the LLM (default: 50).",
    )
    parser.add_argument(
        "--k-min", type=int, default=6, help="Minimum cluster count (default: 6)."
    )
    parser.add_argument(
        "--k-max", type=int, default=16, help="Maximum cluster count (default: 16)."
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=100,
        help="Fold units shorter than this into adjacent (default 100, matches "
        "Drakosfire's v3 recipe).",
    )
    parser.add_argument(
        "--no-merge-chunks",
        action="store_true",
        help="Disable heading-based merging (default: enabled).",
    )
    parser.add_argument(
        "--merge-max-chars",
        type=int,
        default=2000,
        help="Max chars per merged chunk (default 2000, matches Drakosfire's v3).",
    )
    args = parser.parse_args()

    build_self_portrait(
        substrate_dir=args.substrate_dir,
        document_id=args.document_id,
        out_path=args.out,
        corpus_id=args.corpus_id,
        use_llm=not args.no_llm,
        llm_glossary_max_units=args.llm_glossary_max,
        cluster_k_range=(args.k_min, args.k_max),
        recipe_min_chars=args.min_chars,
        recipe_merge_chunks=not args.no_merge_chunks,
        recipe_merge_max_chars=args.merge_max_chars,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
