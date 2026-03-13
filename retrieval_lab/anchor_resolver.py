"""Anchor resolver: deterministic mapping from GoldAnchors to current EvidenceUnit IDs.

Resolution ladder (per anchor):
  1. Cached unit ID direct lookup in corpus
  2. Source unit ID lineage traversal (handles fold/merge)
  3. Page + structural_path + quote overlap matching
  4. Nearby page (±1) + structural_path + quote fallback
  5. Unresolved

Resolution statuses:
  exact       — cached IDs found directly in corpus
  split       — anchor maps to more units than previously cached
  merged      — anchor maps to fewer units than previously cached
  approximate — resolved via quote/path matching, not ID match
  unresolved  — no acceptable match found
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from retrieval_lab.anchor_schema import AnchorResolution, GoldAnchor


def _jaccard_tokens(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    if not a.strip() or not b.strip():
        return 0.0
    ta = set(re.findall(r"[a-z0-9']+", a.casefold()))
    tb = set(re.findall(r"[a-z0-9']+", b.casefold()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _token_overlap_recall(quote: str, text: str) -> float:
    """Anchor-token recall: how much of the quote is contained in text."""
    if not quote.strip() or not text.strip():
        return 0.0
    quote_tokens = set(re.findall(r"[a-z0-9']+", quote.casefold()))
    text_tokens = set(re.findall(r"[a-z0-9']+", text.casefold()))
    if not quote_tokens or not text_tokens:
        return 0.0
    return len(quote_tokens & text_tokens) / len(quote_tokens)


def _normalize_path_parts(parts: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip().casefold() for p in parts if p.strip()]


def _path_tokens(parts: list[str]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in re.findall(r"[a-z0-9']+", part.casefold()):
            tokens.add(token)
    return tokens


def _path_token_overlap_count(a: list[str], b: list[str]) -> int:
    return len(_path_tokens(a) & _path_tokens(b))


def _paths_match(a: list[str], b: list[str]) -> bool:
    """Check if two structural paths match, including suffix matching."""
    na = _normalize_path_parts(a)
    nb = _normalize_path_parts(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return longer[-len(shorter):] == shorter


def _build_source_to_corpus(corpus: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Map original source_unit_ids to their containing corpus unit IDs."""
    mapping: dict[str, list[str]] = {}
    for unit in corpus:
        uid = unit.get("id", "")
        if not uid:
            continue
        for sid in unit.get("source_unit_ids") or []:
            sid = str(sid).strip()
            if sid:
                mapping.setdefault(sid, []).append(uid)
    return mapping


def _build_corpus_by_page(corpus: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_page: dict[int, list[dict[str, Any]]] = {}
    for unit in corpus:
        page = unit.get("page")
        if page is not None:
            by_page.setdefault(int(page), []).append(unit)
    return by_page


def _match_by_path_and_quote(
    anchor: GoldAnchor,
    candidates: list[dict[str, Any]],
    quote_jaccard_threshold: float,
    *,
    quote_recall_threshold: float,
    require_path_match: bool = True,
    min_path_token_overlap: int = 0,
) -> list[tuple[str, float, float, float, int]]:
    """Find corpus units matching anchor's structural_path with sufficient quote overlap."""
    matched: list[tuple[str, float, float, float, int]] = []
    for unit in candidates:
        unit_path = unit.get("structural_path") or []
        path_overlap_tokens = _path_token_overlap_count(anchor.structural_path, unit_path)
        if require_path_match:
            if not _paths_match(anchor.structural_path, unit_path):
                continue
        elif path_overlap_tokens < min_path_token_overlap:
            continue
        jaccard = _jaccard_tokens(anchor.anchor_quote, unit.get("text", ""))
        recall = _token_overlap_recall(anchor.anchor_quote, unit.get("text", ""))
        if jaccard >= quote_jaccard_threshold or recall >= quote_recall_threshold:
            score = max(jaccard, recall)
            matched.append((unit["id"], score, jaccard, recall, path_overlap_tokens))
    matched.sort(key=lambda item: (item[1], item[3], item[2], item[4]), reverse=True)
    return matched


def _score_anchor_against_unit(anchor: GoldAnchor, unit: dict[str, Any]) -> tuple[float, float, bool]:
    """Return (jaccard, recall, path_match) for an anchor-unit pair."""
    jaccard = _jaccard_tokens(anchor.anchor_quote, unit.get("text", ""))
    recall = _token_overlap_recall(anchor.anchor_quote, unit.get("text", ""))
    path_match = _paths_match(anchor.structural_path, unit.get("structural_path") or [])
    return jaccard, recall, path_match


def _disambiguate_lineage_split_with_anchor_content(
    anchor: GoldAnchor,
    corpus_by_page: dict[int, list[dict[str, Any]]],
    quote_threshold: float,
) -> tuple[list[str], dict[str, float], str] | None:
    """Prefer the anchor's own page/path+quote match over split lineage fan-out.

    When source lineage maps an anchor to multiple units, try to pick the
    single unit that best matches the anchor's authored page/path/quote.
    This keeps required-gold semantics stable across chunking changes.
    """
    primary = _match_by_path_and_quote(
        anchor,
        corpus_by_page.get(anchor.page, []),
        quote_threshold,
        quote_recall_threshold=0.85,
        require_path_match=True,
    )
    if primary:
        best = primary[0]
        return (
            [best[0]],
            {"best_quote_overlap": best[2], "best_quote_recall": best[3]},
            "lineage_split_disambiguated_page_path_quote",
        )

    for delta in [-1, 1]:
        nearby_page = anchor.page + delta
        nearby = _match_by_path_and_quote(
            anchor,
            corpus_by_page.get(nearby_page, []),
            quote_threshold,
            quote_recall_threshold=0.85,
            require_path_match=True,
        )
        if nearby:
            best = nearby[0]
            return (
                [best[0]],
                {"best_quote_overlap": best[2], "best_quote_recall": best[3]},
                f"lineage_split_disambiguated_nearby_page_{nearby_page}_path_quote",
            )
    return None


def _arbitrate_exact_lineage_with_local_candidate(
    anchor: GoldAnchor,
    lineage_unit_id: str,
    corpus_by_id: dict[str, dict[str, Any]],
    corpus_by_page: dict[int, list[dict[str, Any]]],
    quote_threshold: float,
) -> tuple[list[str], dict[str, float], str] | None:
    """Swap a weak lineage exact hit for a stronger local quote/path hit.

    This is intentionally conservative: we only switch when the local candidate
    is strongly quote-grounded and materially better than the lineage unit.
    """
    lineage_unit = corpus_by_id.get(lineage_unit_id)
    if lineage_unit is None:
        return None

    local = _disambiguate_lineage_split_with_anchor_content(
        anchor,
        corpus_by_page,
        quote_threshold,
    )
    if local is None:
        return None
    local_ids, local_scores, local_resolved_by = local
    local_id = local_ids[0]
    if local_id == lineage_unit_id:
        return None

    lineage_jaccard, lineage_recall, lineage_path_match = _score_anchor_against_unit(anchor, lineage_unit)
    local_best = max(float(local_scores.get("best_quote_overlap", 0.0)), float(local_scores.get("best_quote_recall", 0.0)))
    lineage_best = max(lineage_jaccard, lineage_recall)

    # Conservative switch condition:
    # - local has very strong quote containment
    # - local materially beats lineage by >= 0.15, OR lineage lacks path match
    if float(local_scores.get("best_quote_recall", 0.0)) < 0.85:
        return None
    if not (local_best >= lineage_best + 0.15 or not lineage_path_match):
        return None

    return (
        [local_id],
        {
            "best_quote_overlap": float(local_scores.get("best_quote_overlap", 0.0)),
            "best_quote_recall": float(local_scores.get("best_quote_recall", 0.0)),
            "lineage_quote_overlap": lineage_jaccard,
            "lineage_quote_recall": lineage_recall,
        },
        f"lineage_exact_arbitrated_to_{local_resolved_by}",
    )


def _resolve_one(
    anchor: GoldAnchor,
    corpus_by_id: dict[str, dict[str, Any]],
    source_to_corpus: dict[str, list[str]],
    corpus_by_page: dict[int, list[dict[str, Any]]],
    substrate_version: str,
    quote_threshold: float,
) -> AnchorResolution:
    """Resolve a single anchor through the resolution ladder."""

    # Step 1: Direct cached_unit_ids lookup
    if anchor.cached_unit_ids:
        found = [uid for uid in anchor.cached_unit_ids if uid in corpus_by_id]
        if found:
            if set(found) == set(anchor.cached_unit_ids):
                return AnchorResolution(
                    anchor_id=anchor.anchor_id,
                    substrate_version=substrate_version,
                    resolved_unit_ids=found,
                    resolution_status="exact",
                    resolved_by="cached_unit_ids",
                )
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                substrate_version=substrate_version,
                resolved_unit_ids=found,
                resolution_status="approximate",
                resolved_by="cached_unit_ids_partial",
            )

    # Step 2: Source unit ID lineage traversal
    if anchor.cached_source_unit_ids:
        resolved_via_lineage: set[str] = set()
        for sid in anchor.cached_source_unit_ids:
            if sid in corpus_by_id:
                resolved_via_lineage.add(sid)
            for corpus_id in source_to_corpus.get(sid, []):
                resolved_via_lineage.add(corpus_id)

        if resolved_via_lineage:
            n_cached = len(anchor.cached_unit_ids) if anchor.cached_unit_ids else 1
            n_resolved = len(resolved_via_lineage)
            if n_resolved > 1:
                disambiguated = _disambiguate_lineage_split_with_anchor_content(
                    anchor,
                    corpus_by_page,
                    quote_threshold,
                )
                if disambiguated is not None:
                    unit_ids, scores, resolved_by = disambiguated
                    return AnchorResolution(
                        anchor_id=anchor.anchor_id,
                        substrate_version=substrate_version,
                        resolved_unit_ids=unit_ids,
                        resolution_status="approximate",
                        resolved_by=resolved_by,
                        resolver_scores=scores,
                    )
            elif n_resolved == 1:
                lineage_uid = next(iter(resolved_via_lineage))
                arbitrated = _arbitrate_exact_lineage_with_local_candidate(
                    anchor,
                    lineage_uid,
                    corpus_by_id,
                    corpus_by_page,
                    quote_threshold,
                )
                if arbitrated is not None:
                    unit_ids, scores, resolved_by = arbitrated
                    return AnchorResolution(
                        anchor_id=anchor.anchor_id,
                        substrate_version=substrate_version,
                        resolved_unit_ids=unit_ids,
                        resolution_status="approximate",
                        resolved_by=resolved_by,
                        resolver_scores=scores,
                    )
            if n_resolved > n_cached:
                status = "split"
            elif n_resolved < n_cached:
                status = "merged"
            else:
                status = "exact"
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                substrate_version=substrate_version,
                resolved_unit_ids=sorted(resolved_via_lineage),
                resolution_status=status,
                resolved_by="source_unit_id_lineage",
            )

    # Step 3: Page + structural_path + quote matching
    candidates = corpus_by_page.get(anchor.page, [])
    matched = _match_by_path_and_quote(
        anchor,
        candidates,
        quote_threshold,
        quote_recall_threshold=0.85,
        require_path_match=True,
    )
    if matched:
        return AnchorResolution(
            anchor_id=anchor.anchor_id,
            substrate_version=substrate_version,
            resolved_unit_ids=[m[0] for m in matched],
            resolution_status="approximate",
            resolved_by="page_path_quote",
            resolver_scores={
                "best_quote_overlap": max(m[2] for m in matched),
                "best_quote_recall": max(m[3] for m in matched),
            },
        )

    # Step 4: Nearby page fallback (±1) with strict path matching.
    for delta in [-1, 1]:
        nearby_page = anchor.page + delta
        candidates = corpus_by_page.get(nearby_page, [])
        matched = _match_by_path_and_quote(
            anchor,
            candidates,
            quote_threshold,
            quote_recall_threshold=0.85,
            require_path_match=True,
        )
        if matched:
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                substrate_version=substrate_version,
                resolved_unit_ids=[m[0] for m in matched],
                resolution_status="approximate",
                resolved_by=f"nearby_page_{nearby_page}_path_quote",
                resolver_scores={
                    "best_quote_overlap": max(m[2] for m in matched),
                    "best_quote_recall": max(m[3] for m in matched),
                },
            )

    # Step 5: Nearby page fallback (±1) with relaxed path constraints and strict quote containment.
    for delta in [-1, 1]:
        nearby_page = anchor.page + delta
        candidates = corpus_by_page.get(nearby_page, [])
        matched = _match_by_path_and_quote(
            anchor,
            candidates,
            max(quote_threshold, 0.18),
            quote_recall_threshold=0.92,
            require_path_match=False,
            min_path_token_overlap=0,
        )
        if matched:
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                substrate_version=substrate_version,
                resolved_unit_ids=[m[0] for m in matched],
                resolution_status="approximate",
                resolved_by=f"nearby_page_{nearby_page}_relaxed_path_quote",
                resolver_scores={
                    "best_quote_overlap": max(m[2] for m in matched),
                    "best_quote_recall": max(m[3] for m in matched),
                },
            )

    # Step 6: Unresolved
    return AnchorResolution(
        anchor_id=anchor.anchor_id,
        substrate_version=substrate_version,
        resolved_unit_ids=[],
        resolution_status="unresolved",
        resolved_by="none",
    )


def resolve_anchors(
    anchors: dict[str, GoldAnchor],
    corpus: list[dict[str, Any]],
    substrate_version: str = "",
    quote_threshold: float = 0.25,
) -> dict[str, AnchorResolution]:
    """Resolve all anchors against the current corpus.

    Returns a dict mapping anchor_id to its AnchorResolution.
    """
    corpus_by_id = {u["id"]: u for u in corpus if u.get("id")}
    source_to_corpus = _build_source_to_corpus(corpus)
    corpus_by_page = _build_corpus_by_page(corpus)

    return {
        anchor_id: _resolve_one(
            anchor, corpus_by_id, source_to_corpus, corpus_by_page,
            substrate_version, quote_threshold,
        )
        for anchor_id, anchor in anchors.items()
    }


def build_resolved_gold_sets(
    queries: list[dict[str, Any]],
    resolutions: dict[str, AnchorResolution],
) -> list[dict[str, Any]]:
    """Populate required_gold / supporting_gold from anchor resolutions.

    Queries without required_anchor_ids pass through unchanged.
    Returns updated query copies with resolved runtime gold fields.
    """
    updated: list[dict[str, Any]] = []
    for query in queries:
        q = dict(query)
        required_anchors = q.get("required_anchor_ids") or []
        supporting_anchors = q.get("supporting_anchor_ids") or []

        if not required_anchors and not supporting_anchors:
            updated.append(q)
            continue

        resolved_required: list[str] = []
        resolved_supporting: list[str] = []

        for aid in required_anchors:
            res = resolutions.get(aid)
            if res and res.resolved_unit_ids:
                resolved_required.extend(res.resolved_unit_ids)

        for aid in supporting_anchors:
            res = resolutions.get(aid)
            if res and res.resolved_unit_ids:
                resolved_supporting.extend(res.resolved_unit_ids)

        resolved_required = list(dict.fromkeys(resolved_required))
        required_set = set(resolved_required)
        resolved_supporting = [
            uid for uid in dict.fromkeys(resolved_supporting)
            if uid not in required_set
        ]

        q["required_gold"] = resolved_required
        q["supporting_gold"] = resolved_supporting
        q["gold_unit_ids"] = resolved_required + resolved_supporting
        q["_required_gold"] = resolved_required
        q["_supporting_gold"] = resolved_supporting

        updated.append(q)

    return updated


def resolution_summary(resolutions: dict[str, AnchorResolution]) -> dict[str, Any]:
    """Compute aggregate statistics over a set of anchor resolutions."""
    by_status: dict[str, int] = {}
    unresolved_anchors: list[str] = []
    for res in resolutions.values():
        by_status[res.resolution_status] = by_status.get(res.resolution_status, 0) + 1
        if res.resolution_status == "unresolved":
            unresolved_anchors.append(res.anchor_id)

    return {
        "total_anchors": len(resolutions),
        "by_status": by_status,
        "all_resolved": len(unresolved_anchors) == 0,
        "unresolved_anchors": unresolved_anchors,
    }


def load_anchors_from_batches(batch_paths: list[str]) -> dict[str, GoldAnchor]:
    """Load all GoldAnchors from benchmark batch files.

    Scans each file for a top-level ``anchors`` dict added by the
    enrichment script, or a sibling ``.anchors.json`` sidecar used for
    root-array benchmark files. Returns empty dict when no anchors exist
    (backward-compatible with pre-anchor benchmarks).
    """
    anchors: dict[str, GoldAnchor] = {}
    for path_str in batch_paths:
        p = Path(path_str)
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        file_anchors: dict[str, Any] = {}
        if isinstance(data, dict):
            file_anchors = data.get("anchors") or {}
        elif isinstance(data, list):
            sidecar = p.with_suffix(".anchors.json")
            if sidecar.exists():
                sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(sidecar_data, dict):
                    file_anchors = sidecar_data.get("anchors") or {}
        for anchor_id, anchor_dict in file_anchors.items():
            if isinstance(anchor_dict, dict) and "anchor_id" in anchor_dict:
                anchors[anchor_id] = GoldAnchor.from_dict(anchor_dict)
    return anchors
