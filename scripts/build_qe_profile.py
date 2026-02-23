#!/usr/bin/env python3
"""Generate a draft QueryExpansionProfile JSON from substrate enrichment outputs.

Aggregates lexical_anchors, surface_forms, structural_path headings, and topic_tags
from Stage A' enrichments and Stage B EvidenceUnits. Synonym sets and term boosters
are emitted as empty stubs for manual curation.

Usage:
    uv run python scripts/build_qe_profile.py \
        --substrate-path out/mark3/SwordsWizardry \
        --corpus-id swcr \
        --document-id SwordsWizardry \
        --output profiles/swcr_v1_qe.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _collect_enrichments(substrate_path: Path) -> list[dict]:
    """Load all stageAPrime.enrichments.json files under substrate_path."""
    enrichments = []
    for f in sorted(substrate_path.rglob("stageAPrime.enrichments.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                enrichments.extend(data.values())
            elif isinstance(data, list):
                enrichments.extend(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping %s: %s", f, e)
    return enrichments


def _collect_evidence_units(substrate_path: Path) -> list[dict]:
    """Load all stageB.evidence_units.json files under substrate_path."""
    units = []
    for f in sorted(substrate_path.rglob("stageB.evidence_units.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                units.extend(data)
            elif isinstance(data, dict):
                # Mark III stageB files are typically envelopes:
                # { "unit_count": int, "units": [...], "gate_diagnostics": [...] }
                if isinstance(data.get("units"), list):
                    units.extend(data["units"])
                else:
                    # Fallback for unexpected shapes
                    units.extend([v for v in data.values() if isinstance(v, dict)])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping %s: %s", f, e)
    return units


def build_profile(
    substrate_path: Path,
    corpus_id: str,
    document_id: str,
    profile_version: str = "0.1.0",
) -> dict:
    """Aggregate enrichment data into a draft profile dict."""
    enrichments = _collect_enrichments(substrate_path)
    units = _collect_evidence_units(substrate_path)

    logger.info("Loaded %d enrichments, %d evidence units", len(enrichments), len(units))

    keywords: set[str] = set()
    entities: set[str] = set()
    topic_counts: Counter[str] = Counter()
    paraphrase_pairs: list[dict] = []

    for enr in enrichments:
        for anchor in enr.get("lexical_anchors", []):
            if isinstance(anchor, str) and anchor.strip():
                keywords.add(anchor.strip().lower())

        for atom in enr.get("mechanic_atoms", []):
            for sf in atom.get("surface_forms", []):
                if isinstance(sf, str) and sf.strip():
                    entities.add(sf.strip().lower())
            sfs = atom.get("surface_forms", [])
            pars = atom.get("paraphrases", [])
            if sfs and pars:
                paraphrase_pairs.append({
                    "surface_forms": sfs[:2],
                    "paraphrases": pars[:2],
                })

        for tag in enr.get("topic_tags", []):
            if isinstance(tag, str):
                topic_counts[tag] += 1

    headings: set[str] = set()
    for unit in units:
        for segment in unit.get("structural_path", []):
            if isinstance(segment, str) and segment.strip():
                headings.add(segment.strip())

    profile = {
        "profile_id": f"{corpus_id}_v1_qe_001",
        "corpus_id": corpus_id,
        "corpus_hash": "",
        "profile_version": profile_version,
        "normalization": {
            "lowercase": True,
            "unicode_nfkc": True,
            "strip_punct": False,
            "dice_normalization": True,
            "stopword_policy": "none",
        },
        "synonym_sets": [],
        "term_boosters": [],
        "allowed_vocab": {
            "top_keywords": sorted(keywords),
            "headings": sorted(headings),
            "entities": sorted(entities),
        },
        "policies": {
            "max_expanded_queries": 3,
            "include_original": True,
            "require_facet_diversity": True,
            "drift_guard": {
                "enabled": False,
                "method": "lexical_overlap",
                "threshold": 0.3,
            },
        },
        "decomposition": {
            "enabled": False,
            "max_subqueries": 3,
            "when": "multi_hop_only",
        },
        "llm_rewrite": {
            "enabled": False,
            "model_id": "",
            "temperature": 0.0,
            "top_p": 1.0,
            "prompt_template_id": "",
            "prompt_hash": "",
            "output_schema_version": "v1",
        },
        "cache": {
            "enabled": True,
            "cache_dir": ".qe_cache",
        },
        "_generation_metadata": {
            "source": "build_qe_profile.py",
            "document_id": document_id,
            "enrichment_count": len(enrichments),
            "evidence_unit_count": len(units),
            "keyword_count": len(keywords),
            "entity_count": len(entities),
            "heading_count": len(headings),
            "top_topic_tags": topic_counts.most_common(15),
            "sample_paraphrase_pairs": paraphrase_pairs[:10],
        },
    }
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft QueryExpansionProfile from substrate enrichments")
    parser.add_argument("--substrate-path", required=True, help="Path to substrate directory")
    parser.add_argument("--corpus-id", required=True, help="Corpus identifier (e.g., swcr)")
    parser.add_argument("--document-id", required=True, help="Document ID (e.g., SwordsWizardry)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--profile-version", default="0.1.0", help="Profile version string")
    args = parser.parse_args()

    substrate_path = Path(args.substrate_path)
    if not substrate_path.is_dir():
        logger.error("Substrate path not found: %s", substrate_path)
        sys.exit(1)

    profile = build_profile(substrate_path, args.corpus_id, args.document_id, args.profile_version)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Profile written to %s (%d keywords, %d entities, %d headings)",
        output_path,
        len(profile["allowed_vocab"]["top_keywords"]),
        len(profile["allowed_vocab"]["entities"]),
        len(profile["allowed_vocab"]["headings"]),
    )


if __name__ == "__main__":
    main()
