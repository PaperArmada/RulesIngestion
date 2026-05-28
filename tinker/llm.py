"""Ollama-backed LLM wrapper for intent-routed retrieval.

Centralizes role-to-model bindings and per-role thinking-mode defaults so
individual call sites don't drift. See
Docs/Design/MODELS-Intent-Routed-Retrieval.md for the lineup and rationale.

Every role function accepts a `think` override; pass None to use the
role default, True/False to force.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import ollama


MODEL_CLASSIFIER = "qwen3:4b"
MODEL_WORKHORSE = "qwen3:14b"
MODEL_EMBEDDER = "qwen3-embedding"


DEFAULT_THINK: dict[str, bool] = {
    "classify": False,
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
    model: str,
    messages: list[dict[str, str]],
    *,
    think: bool,
    json_format: bool = False,
    options: dict[str, Any] | None = None,
) -> LLMResult:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "think": think,
    }
    if json_format:
        kwargs["format"] = "json"
    if options:
        kwargs["options"] = options
    resp = ollama.chat(**kwargs)
    return LLMResult(text=resp["message"]["content"], raw=dict(resp))


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
    """Classify a query into one of the retrieval buckets.

    Returns a dict with keys: bucket, confidence, reason. Raises
    json.JSONDecodeError if the model produces invalid JSON despite
    format=json.
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
        MODEL_CLASSIFIER,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
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
    """Read a query, output an intent statement plus 1-3 target cluster ids.

    Returns dict: {intent: str, target_clusters: list[str], reason: str}.
    """
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
    result = _chat(
        MODEL_WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        think=_resolve_think("extract_intent", think),
        json_format=True,
    )
    return json.loads(result.text)


def hypothesize(
    query: str,
    target_shape_description: str,
    glossary_terms: list[str],
    *,
    think: bool | None = None,
) -> str:
    """Generate a hypothetical answer-shaped artifact for HyDE embedding.

    Produces text in the target structural shape, using glossary terms
    where natural. The hypothesis is intended for embedding, not for
    showing to a user.
    """
    system = (
        "You generate a hypothetical answer-shaped artifact whose purpose "
        "is to bridge a user query to corpus evidence in embedding space. "
        "The hypothesis must look like the target structural shape, not "
        "generic prose, and should use the provided vocabulary where it "
        "fits naturally. Do not write disclaimers; produce only the "
        "artifact itself."
    )
    user = (
        f"Target structural shape:\n{target_shape_description}\n\n"
        f"Glossary terms (use where they fit): {', '.join(glossary_terms) if glossary_terms else '(none provided)'}\n\n"
        f"User query: {query}\n\n"
        "Generate the hypothetical artifact now."
    )
    result = _chat(
        MODEL_WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        think=_resolve_think("hypothesize", think),
    )
    return result.text.strip()


def synthesize(
    query: str,
    evidence: list[str],
    *,
    think: bool | None = None,
) -> str:
    """Generate a final answer from retrieved evidence.

    Each evidence string is shown with a bracketed index; the model is
    instructed to cite that index for each claim.
    """
    system = (
        "Answer the user's question using ONLY the provided evidence. "
        "Cite the bracketed evidence index for each claim, e.g. [2]. "
        "If the evidence is insufficient to answer, say so explicitly "
        "and identify what is missing."
    )
    evidence_block = "\n\n".join(f"[{i}] {chunk}" for i, chunk in enumerate(evidence))
    user = f"Evidence:\n{evidence_block}\n\nQuestion: {query}"
    result = _chat(
        MODEL_WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        think=_resolve_think("synthesize", think),
    )
    return result.text.strip()


def extract_glossary(
    chunk_text: str,
    *,
    think: bool | None = None,
) -> dict[str, Any]:
    """Extract term-definition pairs and acronym expansions from a chunk.

    Returns dict: {terms: list[{term, definition}], acronyms: list[{acronym, expansion}]}.
    """
    system = (
        "You extract glossary-style term-definition pairs and acronym "
        "expansions from a passage of rulebook text. Include only items "
        "the passage itself defines or expands. Respond ONLY with JSON of "
        'the form: {"terms": [{"term": str, "definition": str}], '
        '"acronyms": [{"acronym": str, "expansion": str}]}.'
    )
    user = f"Passage:\n{chunk_text}"
    result = _chat(
        MODEL_WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        think=_resolve_think("extract_glossary", think),
        json_format=True,
    )
    return json.loads(result.text)


def label_cluster(
    exemplars: list[str],
    *,
    think: bool | None = None,
) -> str:
    """Describe a structural cluster's shape in one sentence."""
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
        MODEL_WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        think=_resolve_think("label_cluster", think),
    )
    return result.text.strip()


def embed(texts: Iterable[str]) -> list[list[float]]:
    """Batch-embed texts with the embedding model.

    Returns one vector per input, in input order. Uses Ollama's batched
    embed API.
    """
    items = list(texts)
    if not items:
        return []
    resp = ollama.embed(model=MODEL_EMBEDDER, input=items)
    return [list(vec) for vec in resp["embeddings"]]


def smoke_test() -> None:
    """Quick end-to-end sanity check. Run as `python -m tinker.llm`.

    Verifies the wrapper can reach Ollama and exercise each role with
    trivial inputs. Prints results to stdout.
    """
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
