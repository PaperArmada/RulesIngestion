"""LLM wrapper for intent-routed retrieval.

Role functions (classify, extract_intent, hypothesize, synthesize,
extract_glossary, label_cluster) dispatch through `tinker.backends`. The
backend is selected by the TINKER_LLM_BACKEND env var (ollama | gemini).

Embedding stays on Ollama regardless of backend choice. Hosted embeddings
are a separate decision that hasn't been made yet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import ollama

from tinker.backends import ChatResult, current_backend
from tinker.backends.ollama_backend import (
    MODEL_CLASSIFIER,
    MODEL_WORKHORSE,
    _unload_ollama_model,
)
from tinker.runtime_config import CFG


MODEL_EMBEDDER = "qwen3-embedding"


DEFAULT_THINK: dict[str, bool] = {
    "classify": False,
    "classify_qrofs": False,
    "extract_intent": False,
    "hypothesize": False,
    "synthesize": False,
    "extract_glossary": True,
    "label_cluster": True,
}


@dataclass(frozen=True)
class LLMResult:
    text: str
    raw: dict[str, Any]


def _chat(
    role: str,
    system: str,
    user: str,
    *,
    think: bool,
    json_format: bool = False,
    max_tokens: int | None = None,
) -> ChatResult:
    """Dispatch one chat turn through the configured backend."""
    return current_backend().chat(
        role=role,
        system=system,
        user=user,
        think=think,
        json_format=json_format,
        max_tokens=max_tokens,
    )


def _resolve_think(role: str, override: bool | None) -> bool:
    if override is not None:
        return override
    return DEFAULT_THINK[role]


def classify(
    query: str,
    self_portrait: str,
    buckets: list[str],
    *,
    think: bool | None = None,
) -> dict[str, Any]:
    """Smoke-test classifier. The production classifier lives in
    `tinker.routing.classifier`; this stays for `python -m tinker.llm`.
    """
    system = (
        "You are a query classifier for a retrieval system. Given a user "
        "query and a corpus self-portrait, choose the single most "
        "appropriate retrieval bucket from the list, report your "
        "confidence (0.0-1.0), and give a brief reason. Respond ONLY "
        'with JSON of the form: {"bucket": str, "confidence": float, "reason": str}.'
    )
    user = (
        f"Corpus self-portrait:\n{self_portrait}\n\n"
        f"Available buckets:\n- " + "\n- ".join(buckets) + "\n\n"
        f"Query: {query}"
    )
    result = _chat(
        "classify",
        system,
        user,
        think=_resolve_think("classify", think),
        json_format=True,
    )
    return json.loads(result.text)


def extract_intent(
    query: str,
    structural_inventory: str,
    *,
    think: bool | None = None,
) -> dict[str, Any]:
    system = (
        "You analyze a user query against a corpus's structural inventory "
        "to identify (a) what intent the query expresses and (b) which "
        "1-3 structural clusters of the corpus would contain content "
        "satisfying that intent. Respond ONLY with JSON of the form: "
        '{"intent": str, "target_clusters": list[str], "reason": str}.'
    )
    user = (
        f"Structural inventory:\n{structural_inventory}\n\nQuery: {query}"
    )
    # think: explicit override wins; otherwise the CFG knob (default off).
    use_think = CFG.think_intent if think is None else think
    result = _chat(
        "extract_intent",
        system,
        user,
        think=use_think,
        json_format=True,
    )
    return json.loads(result.text)


def hypothesize(
    query: str,
    target_shape_description: str,
    glossary_terms: list[str],
    *,
    think: bool | None = None,
    max_tokens: int | None = None,
) -> str:
    """Generate a hypothesis-shaped artifact for HyDE embedding.

    The token cap and word limit come from CFG (hypothesis_max_tokens /
    hypothesis_word_limit) unless overridden. The 200-token / 120-word
    default was a local-latency accommodation; hosted models can afford a
    richer hypothesis, which may embed closer to the target evidence.
    """
    cap = CFG.hypothesis_max_tokens if max_tokens is None else max_tokens
    word_limit = CFG.hypothesis_word_limit
    system = (
        "You generate a hypothetical answer-shaped artifact whose purpose "
        "is to bridge a user query to corpus evidence in embedding space. "
        "The hypothesis must look like the target structural shape, not "
        "generic prose, and should use the provided vocabulary where it "
        f"fits naturally. Be concise: under {word_limit} words. Do not write "
        "disclaimers, do not restate the question; produce only the "
        "artifact itself."
    )
    user = (
        f"Target structural shape:\n{target_shape_description}\n\n"
        f"Glossary terms (use where they fit): {', '.join(glossary_terms) if glossary_terms else '(none provided)'}\n\n"
        f"User query: {query}\n\n"
        f"Generate the hypothetical artifact now (under {word_limit} words)."
    )
    result = _chat(
        "hypothesize",
        system,
        user,
        think=_resolve_think("hypothesize", think),
        max_tokens=cap,
    )
    return result.text.strip()


def resolve_facet(
    query: str,
    facet_schema: str,
    *,
    think: bool | None = None,
) -> dict[str, Any]:
    """Map a query to ONE enumerable facet value from a discovered catalog.

    The catalog is built from schema-free facet discovery (corpus-specific
    but auto-discovered, not hardcoded). Returns
    {is_enumeration: bool, channel: str|null, value: str|null, reason: str}.
    `channel` and `value` must be copied from the catalog; the route validates.
    """
    system = (
        "You map a user query to ONE enumerable facet value from a catalog of "
        "facets discovered in a corpus. A facet value defines a complete SET of "
        "items sharing an attribute value (e.g. all items at a given level). "
        "If the query asks to enumerate / list / count the complete set of items "
        "sharing one attribute value, return that facet's channel and the exact "
        "value token from the catalog. If the query is NOT a set-completion "
        "request, set is_enumeration to false. Respond ONLY with JSON: "
        '{"is_enumeration": bool, "channel": str|null, "value": str|null, '
        '"reason": str}. The channel must be copied exactly from the catalog, '
        "and the value must be one of that channel's listed tokens."
    )
    user = f"Facet catalog:\n{facet_schema}\n\nQuery: {query}"
    result = _chat(
        "resolve_facet",
        system,
        user,
        think=False if think is None else think,
        json_format=True,
    )
    return json.loads(result.text)


def paraphrase_query(question: str, *, think: bool | None = None) -> str:
    """Rewrite a templated enumeration query as natural user phrasing.

    Used only for eval prep: it tests the facet resolver on phrasing it did not
    generate from. Preserves the exact attribute and value; avoids copying the
    field label verbatim so resolution must be semantic, not a template reversal.
    """
    system = (
        "Rewrite the request as a natural question a real user would ask. "
        "Preserve the EXACT attribute and value being requested, but do NOT copy "
        "the field label verbatim — use natural synonyms and phrasing. Keep it a "
        "clear request to list/enumerate the complete set. Output only the "
        "rewritten question, nothing else."
    )
    result = _chat(
        "paraphrase",
        system,
        f"Request: {question}",
        think=False if think is None else think,
    )
    return result.text.strip()


def synthesize(
    query: str,
    evidence: list[str],
    *,
    think: bool | None = None,
) -> str:
    system = (
        "Answer the user's question using ONLY the provided evidence. "
        "Cite the bracketed evidence index for each claim, e.g. [2]. "
        "If the evidence is insufficient to answer, say so explicitly "
        "and identify what is missing."
    )
    evidence_block = "\n\n".join(f"[{i}] {chunk}" for i, chunk in enumerate(evidence))
    user = f"Evidence:\n{evidence_block}\n\nQuestion: {query}"
    result = _chat(
        "synthesize",
        system,
        user,
        think=_resolve_think("synthesize", think),
    )
    return result.text.strip()


def extract_glossary(
    chunk_text: str,
    *,
    think: bool | None = None,
) -> dict[str, Any]:
    system = (
        "You extract glossary-style term-definition pairs and acronym "
        "expansions from a passage of rulebook text. Include only items "
        "the passage itself defines or expands. Respond ONLY with JSON of "
        'the form: {"terms": [{"term": str, "definition": str}], '
        '"acronyms": [{"acronym": str, "expansion": str}]}.'
    )
    user = f"Passage:\n{chunk_text}"
    result = _chat(
        "extract_glossary",
        system,
        user,
        think=_resolve_think("extract_glossary", think),
        json_format=True,
    )
    return json.loads(result.text)


def label_cluster(
    exemplars: list[str],
    *,
    think: bool | None = None,
) -> str:
    system = (
        "You describe the structural form of a cluster of corpus chunks "
        "in a single sentence. Focus on layout and recurring fields "
        "(headings, labeled rows, ladders of outcomes, tables), not on "
        "the topic of the example. The description will be used to route "
        "future queries, so it must generalize across the cluster."
    )
    user = (
        "Exemplar chunks (drawn from the same structural cluster):\n\n"
        + "\n\n---\n\n".join(exemplars)
        + "\n\nDescribe the structural shape in one sentence."
    )
    result = _chat(
        "label_cluster",
        system,
        user,
        think=_resolve_think("label_cluster", think),
    )
    return result.text.strip()


def unload_workhorse() -> bool:
    """Evict the workhorse LLM from the GPU (Ollama). Hosted backends no-op."""
    return current_backend().unload_chat("workhorse")


def unload_ollama_model(model: str, *, wait_seconds: float = 10.0) -> bool:
    """Direct Ollama eviction by model name. Used for the embedder
    (always local) regardless of which LLM backend is configured.
    """
    return _unload_ollama_model(model, wait_seconds=wait_seconds)


def embed(texts: Iterable[str]) -> list[list[float]]:
    """Batch-embed via Ollama's qwen3-embedding. Always local."""
    items = list(texts)
    if not items:
        return []
    resp = ollama.embed(model=MODEL_EMBEDDER, input=items)
    return [list(vec) for vec in resp["embeddings"]]


def smoke_test() -> None:
    """Quick end-to-end sanity check against the current backend."""
    from tinker.backends import current_backend as _cb
    print(f"== backend: {_cb().name} ==")

    print("== embed ==")
    vecs = embed(["Healing Word is a spell.", "Sidestep is a reaction."])
    print(f"  got {len(vecs)} vectors, dim={len(vecs[0])}")

    print("== classify ==")
    out = classify(
        query="What does Healing Word do?",
        self_portrait="Corpus contains spell entries (level, casting time, range, duration, description) and action entries (trigger, effect, success ladder).",
        buckets=[
            "entity_anchored_single",
            "entity_anchored_composite",
            "concept_anchored",
            "intent_bearing_distributed",
            "enumeration",
            "structural",
            "cross_reference",
            "example_based",
        ],
    )
    print(f"  {out}")

    print("== hypothesize ==")
    h = hypothesize(
        query="How do I move away from someone in melee without getting hit?",
        target_shape_description="Action entry: name, traits, requirements, trigger, effect.",
        glossary_terms=["Disengage", "opportunity attack", "reaction"],
    )
    print(f"  {h[:200]}...")

    print("OK")


if __name__ == "__main__":
    smoke_test()
