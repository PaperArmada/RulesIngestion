"""Enrichment planning utilities."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel

from config_generator import RulesetConfiguration


class EnrichmentPlan(BaseModel):
    ruleset_id: str
    chapter_id: str
    doc_signature: str
    deterministic_steps: List[str]
    nondeterministic_steps: List[str]
    nondeterministic_targets: List[Dict[str, Any]]


def _match_flags(text: str, flags: List[str]) -> bool:
    lowered = text.lower()
    return any(flag in lowered for flag in flags)


def build_enrichment_plan(
    ruleset_id: str,
    chapter_id: str,
    doc_signature: str,
    blocks: List[Dict[str, Any]],
    config: RulesetConfiguration,
) -> EnrichmentPlan:
    flags = [flag.lower() for flag in config.nondeterministic_flags]
    nondeterministic_targets: List[Dict[str, Any]] = []

    for block in blocks:
        block_id = block.get("id")
        paragraphs = block.get("paragraphs", [])
        for index, paragraph in enumerate(paragraphs):
            if flags and _match_flags(paragraph, flags):
                nondeterministic_targets.append(
                    {
                        "block_id": block_id,
                        "paragraph_index": index,
                        "text": paragraph,
                    }
                )

    deterministic_steps = ["rule_based_enrichment"]
    nondeterministic_steps = ["llm_enrichment"] if nondeterministic_targets else []

    return EnrichmentPlan(
        ruleset_id=ruleset_id,
        chapter_id=chapter_id,
        doc_signature=doc_signature,
        deterministic_steps=deterministic_steps,
        nondeterministic_steps=nondeterministic_steps,
        nondeterministic_targets=nondeterministic_targets,
    )
