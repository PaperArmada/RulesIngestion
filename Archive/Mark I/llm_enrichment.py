"""LLM enrichment helpers for chunk annotations."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from config_generator import RulesetConfiguration
from enrichment import EnrichedChunk

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise RuntimeError("openai package is required for LLM enrichment.") from exc


DEFAULT_LLM_MODEL = "gpt-5-chat-latest"
QUERY_TYPE_BY_KIND = {
    "spell": "spell.effect",
    "feat": "feat.requirements",
    "item": "item.effect",
    "rule": "rule.summary",
    "table": "table.lookup",
    "narrative": "lore.summary",
    "other": "general.summary",
}


def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _chunk_label(text: str, max_len: Optional[int] = 80) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped if max_len is None else stripped[:max_len]
    return text.strip() if max_len is None else text.strip()[:max_len]


def _build_query_text(kind: str, label: str, template: Optional[str] = None) -> str:
    if not label:
        return f"{kind} rules"
    if template:
        return template.replace("{label}", label)
    if kind == "spell":
        return f"What does {label} do?"
    if kind == "feat":
        return f"What are the requirements for {label}?"
    if kind == "item":
        return f"How does {label} work?"
    if kind == "table":
        return f"Lookup values for {label}"
    if kind == "rule":
        return f"What is the rule about {label}?"
    if kind == "narrative":
        return f"Summarize {label}"
    return f"Explain {label}"


def _resolve_query_type(kind: str, config: Optional[RulesetConfiguration]) -> str:
    base_map = QUERY_TYPE_BY_KIND
    if config:
        defaults = config.deterministic_rules.get("evaluation_query_type_defaults", {})
        if isinstance(defaults, dict) and defaults:
            base_map = defaults
        overrides = config.deterministic_rules.get("evaluation_query_type_overrides", {})
        if isinstance(overrides, dict) and kind in overrides:
            return overrides[kind]
    return base_map.get(kind, "general.summary")


def _resolve_query_template(kind: str, config: Optional[RulesetConfiguration]) -> Optional[str]:
    if config:
        templates = config.deterministic_rules.get("evaluation_query_templates", {})
        if isinstance(templates, dict):
            if kind in templates:
                return templates[kind]
            return templates.get("default")
    return None


def _build_hypothetical_answer(
    text: str,
    max_chars: int = 800,
    strategy: str = "first_paragraph",
) -> str:
    if not text:
        return ""
    if strategy == "full_text":
        answer = text.strip()
    else:
        paragraphs = split_paragraphs(text)
        answer = paragraphs[0] if paragraphs else text.strip()
    if len(answer) > max_chars:
        trimmed = answer[:max_chars]
        return trimmed.rsplit(" ", 1)[0] if " " in trimmed else trimmed
    return answer


def generate_evaluation_queries(
    chunks: List[EnrichedChunk],
    max_per_kind: int = 50,
    config: Optional[RulesetConfiguration] = None,
) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    queries: List[Dict[str, Any]] = []
    if config:
        max_override = config.deterministic_rules.get("evaluation_query_max_per_kind")
        if isinstance(max_override, int) and max_override > 0:
            max_per_kind = max_override
    answer_max_chars = 800
    answer_strategy = "first_paragraph"
    if config:
        configured_max = config.deterministic_rules.get("evaluation_hypothetical_answer_max_chars")
        if isinstance(configured_max, int) and configured_max > 0:
            answer_max_chars = configured_max
        configured_strategy = config.deterministic_rules.get("evaluation_hypothetical_answer_strategy")
        if configured_strategy in {"first_paragraph", "full_text"}:
            answer_strategy = configured_strategy

    for chunk in chunks:
        kind = chunk.content_kind or "other"
        counts.setdefault(kind, 0)
        if counts[kind] >= max_per_kind:
            continue
        label = _chunk_label(chunk.text)
        full_label = _chunk_label(chunk.text, max_len=None)
        query_type = _resolve_query_type(kind, config)
        template = _resolve_query_template(kind, config)
        queries.append(
            {
                "id": f"{chunk.id}::{query_type}",
                "query_text": _build_query_text(kind, full_label, template),
                "query_text_short": _build_query_text(kind, label, template),
                "query_type": query_type,
                "content_kind": kind,
                "hypothetical_answer": _build_hypothetical_answer(
                    chunk.text,
                    max_chars=answer_max_chars,
                    strategy=answer_strategy,
                ),
                "expected_chunk_ids": [chunk.id],
            }
        )
        counts[kind] += 1

    return queries


def extract_paragraph_targets(
    chunks: List[EnrichedChunk],
    config: RulesetConfiguration,
    min_chars: int = 40,
) -> List[Dict[str, Any]]:
    flags = [flag.lower() for flag in config.nondeterministic_flags]
    targets: List[Dict[str, Any]] = []
    configured_min = config.deterministic_rules.get("evaluation_paragraph_min_chars")
    if isinstance(configured_min, int) and configured_min > 0:
        min_chars = configured_min

    if not flags:
        return targets

    for chunk in chunks:
        paragraphs = split_paragraphs(chunk.text)
        for idx, paragraph in enumerate(paragraphs):
            if len(paragraph) < min_chars:
                continue
            lowered = paragraph.lower()
            if any(flag in lowered for flag in flags):
                targets.append(
                    {
                        "chunk_id": chunk.id,
                        "paragraph_index": idx,
                        "text": paragraph,
                        "content_kind": chunk.content_kind,
                        "section_path": chunk.section_path,
                    }
                )

    return targets


def build_paragraph_prompt(target: Dict[str, Any]) -> str:
    return (
        "You are annotating a paragraph from a TTRPG rulebook. "
        "Return ONLY JSON with fields: summary, tags, action_economy, prerequisites.\n\n"
        f"Paragraph:\n{target['text']}\n"
    )


def build_review_prompt(chunk: Dict[str, Any]) -> str:
    return (
        "You are reviewing a coalesced TTRPG chunk. "
        "Return ONLY JSON with fields: summary, key_rules, action_economy, prerequisites, "
        "tags, query.\n\n"
        f"Chunk:\n{chunk['text']}\n"
    )


def _call_llm(prompt: str, model: str, api_key: str, temperature: float = 0.2) -> Dict[str, Any]:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def run_paragraph_enrichment(
    targets: List[Dict[str, Any]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for paragraph enrichment.")

    model = model or os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL)
    results: List[Dict[str, Any]] = []

    for target in targets:
        prompt = build_paragraph_prompt(target)
        annotation = _call_llm(prompt, model, api_key)
        results.append(
            {
                "chunk_id": target["chunk_id"],
                "paragraph_index": target["paragraph_index"],
                "content_kind": target["content_kind"],
                "section_path": target["section_path"],
                "annotation": annotation,
            }
        )

    return results


def run_review_enrichment(
    coalesced_chunks: List[Dict[str, Any]],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for review enrichment.")

    model = model or os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL)
    results: List[Dict[str, Any]] = []
    total = len(coalesced_chunks) if limit is None else min(limit, len(coalesced_chunks))
    print(f"🔎 Starting LLM review pass ({total} chunks)...")

    for idx, chunk in enumerate(coalesced_chunks):
        if limit is not None and idx >= limit:
            break
        if idx % 5 == 0:
            print(f"🤖 LLM review progress: {idx + 1}/{total}")
        prompt = build_review_prompt(chunk)
        annotation = _call_llm(prompt, model, api_key)
        results.append(
            {
                "chunk_id": chunk["id"],
                "section_path": chunk.get("section_path", []),
                "annotation": annotation,
            }
        )

    print(f"✅ LLM review pass complete ({len(results)} chunks).")
    return results
