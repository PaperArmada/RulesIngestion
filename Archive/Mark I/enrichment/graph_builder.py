"""Graph building utilities for enriched chunks.

Pipeline boundary (incremental refactor):
  Phase 0: _build_structural_seed / _apply_structural_seed — doc/section/chunk + contains/next only.
  Phase 1: extract_entity_candidates — pure CandidateBundle (no graph, no canonicalization).
  Phase 2: canonicalize_candidates — pure CanonicalizationResult (alias resolution, candidate→canonical).
  Phase 3: EntityRegistry + materialization — entity nodes and describes/mentioned_in.
  Phase 5: _assign_fact_ownership — belongs_to, procedure anchoring; _apply_phase1_polish — final.
  Public API unchanged: build_chunk_graph(...) -> Graph, build_fact_graph(...) -> Graph.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Pattern, Set, Tuple

from .chunks import EnrichedChunk
from .extractors import extract_feat_title_from_text, extract_spell_title_from_text, normalize_space

if TYPE_CHECKING:
    from .fact_relations import FactRelation
    from .rule_facts import RuleFact


# -----------------------------------------------------------------------------
# Phase pipeline data shapes (incremental refactor boundary)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralSeed:
    """Phase 0 output: document/section/chunk nodes and contains/next edges only."""

    doc_node: Dict[str, Any]
    section_nodes: List[Dict[str, Any]]
    chunk_nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    section_index: Dict[str, str]  # section_key -> section_node_id
    chunk_order: List[str]


class CandidateKind(str, Enum):
    """Kind of entity candidate (Phase 1)."""

    ENTITY = "entity"
    MECHANIC_FRAME = "mechanic_frame"
    TRAIT = "trait"
    TRADITION = "tradition"
    TAG = "tag"
    SPELL_RANK = "spell_rank"
    SPELL_STAT = "spell_stat"
    CONCEPT = "concept"
    PROCEDURE = "procedure"


@dataclass(frozen=True)
class EntityCandidate:
    """Phase 1: single entity candidate before canonicalization."""

    candidate_id: str
    kind: CandidateKind
    entity_type: str
    surface_name: str
    chunk_id: str
    page: Optional[int]
    clause_id: Optional[str]
    extraction_method: str
    semantic: bool
    context: Dict[str, Any]
    confidence: float = 1.0


@dataclass(frozen=True)
class CandidateBundle:
    """Phase 1 output: candidates + relation mentions (targets as names)."""

    candidates: List[EntityCandidate]
    relation_mentions: List[Tuple[str, str, str]]  # (source_id, relation, target_surface_name)


@dataclass(frozen=True)
class CanonicalEntity:
    """Phase 2: canonical entity record."""

    canonical_id: str
    entity_type: str
    name: str
    canonical_key: str
    aliases: List[str]
    entity_role: str
    provenance: Dict[str, Any]


@dataclass(frozen=True)
class CanonicalizationResult:
    """Phase 2 output: alias map, canonical entities, candidate→canonical mapping."""

    alias_map: Dict[str, str]
    canonical_entities: Dict[str, CanonicalEntity]
    candidate_to_canonical: Dict[str, str]
    namekey_to_canonical: Dict[str, str]


@dataclass(frozen=True)
class MaterializedIndexes:
    """Phase 3 output: indexes for later phases (ownership, polish)."""

    entity_type_by_id: Dict[str, str]
    entity_name_by_id: Dict[str, str]
    chunk_to_entities: Dict[str, List[str]]
    describes_meta: Dict[Tuple[str, str], Dict[str, Any]]


@dataclass(frozen=True)
class OwnershipResult:
    """Phase 5: fact ownership assignment result."""

    fact_owner_by_id: Dict[str, str]
    fact_chunk_by_id: Dict[str, str]
    multi_candidate_fact_ids: Set[str]
    missing_candidate_fact_ids: Set[str]


@dataclass
class GraphDelta:
    """Accumulated graph changes for a pass (nodes, edges, node patches)."""

    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    node_updates: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)


def _merge_patch_into_node(node: Dict[str, Any], patch: Dict[str, Any]) -> None:
    """Merge patch into node: list fields extended (dedupe); scalars/dicts set only if missing."""
    for k, v in patch.items():
        if k in node and isinstance(node[k], list) and isinstance(v, list):
            for x in v:
                if x not in node[k]:
                    node[k].append(x)
        elif k not in node or node.get(k) is None or node.get(k) == "":
            node[k] = v
        # else: leave existing scalar/dict (e.g. mechanic_kind already set)


def apply_delta(graph: Graph, delta: GraphDelta) -> None:
    """Apply a delta to the graph (append nodes/edges, patch existing nodes). O(1) node patch via node_index."""
    for node in delta.nodes:
        graph.nodes.append(node)
        nid = node.get("id")
        if nid is not None:
            graph.node_index[nid] = len(graph.nodes) - 1
    for edge in delta.edges:
        graph.edges.append(edge)
    for node_id, patch in delta.node_updates:
        idx = graph.node_index.get(node_id)
        if idx is not None:
            _merge_patch_into_node(graph.nodes[idx], patch)


class EntityRegistry:
    """
    Owns canonical entity id creation, provenance, and namekey indexing.
    Emits GraphDeltas so the graph is not mutated directly from entity logic.
    """

    def __init__(self, doc_id: str, resolved_ruleset_id: str) -> None:
        self.doc_id = doc_id
        self.resolved_ruleset_id = resolved_ruleset_id
        self._seen_ids: Set[str] = set()
        self.namekey_to_id: Dict[str, str] = {}

    def ensure_entity_node(
        self,
        entity_type: str,
        resolved_name: str,
        alias_source: Optional[str],
        chunk_id: str,
        page: Optional[int],
        extraction_method: str,
        mechanic_meta: Dict[str, object],
        chunk_spell_rank: Optional[int],
        chunk_spell_stats: Optional[Dict[str, Any]],
        chunk_traits: List[str],
        chunk_traditions: List[str],
        chunk_tags: List[str],
    ) -> Tuple[str, GraphDelta, bool]:
        """
        Return (canonical_id, delta, is_new). Delta is either new node+mentions edge or node_updates (provenance/aliases).
        Updates self._seen_ids and self.namekey_to_id.
        """
        canonical_key = _normalize_entity_key(resolved_name)
        canonical_id = _canonical_entity_id(
            self.resolved_ruleset_id,
            entity_type,
            resolved_name,
            fallback_key=f"{self.doc_id}:{chunk_id}:{entity_type}",
        )
        entity_role = (
            "mechanic_frame" if entity_type in MECHANIC_FRAME_TYPES else "entity"
        )

        if canonical_id not in self._seen_ids:
            self._seen_ids.add(canonical_id)
            _add_entity_index(self.namekey_to_id, canonical_id, [resolved_name])
            node_payload: Dict[str, Any] = {
                "name": resolved_name,
                "normalized_name": _normalize_entity_name(resolved_name),
                "canonical_key": canonical_key,
                "canonical_id": canonical_id,
                "ruleset_id": self.resolved_ruleset_id,
                "entity_role": entity_role,
                "aliases": [resolved_name],
                "source_documents": [self.doc_id],
                "source_chunk_ids": [chunk_id],
                "source_pages": [page] if page is not None else [],
                "extraction_method": extraction_method,
                "spell_rank": chunk_spell_rank,
                "spell_stats": chunk_spell_stats,
                "traits": chunk_traits,
                "traditions": chunk_traditions,
                "tags": chunk_tags,
                **mechanic_meta,
            }
            delta = GraphDelta(
                nodes=[{"id": canonical_id, "type": entity_type, **node_payload}],
                edges=[
                    {
                        "source": self.doc_id,
                        "target": canonical_id,
                        "relation": "mentions",
                        "source_document": self.doc_id,
                        "page": page,
                        "source_chunk_id": chunk_id,
                        "extraction_method": extraction_method,
                    }
                ],
            )
            return canonical_id, delta, True

        _add_entity_index(
            self.namekey_to_id,
            canonical_id,
            [resolved_name, alias_source] if alias_source else [resolved_name],
        )
        # Emit node_updates so caller applies via apply_delta (no direct graph mutation)
        patch: Dict[str, Any] = {
            "source_documents": [self.doc_id],
            "source_chunk_ids": [chunk_id],
            "source_pages": [page] if page is not None else [],
        }
        if alias_source or resolved_name:
            patch["aliases"] = [resolved_name, alias_source] if alias_source else [resolved_name]
        if entity_type in MECHANIC_FRAME_TYPES and mechanic_meta:
            patch["mechanic_kind"] = mechanic_meta.get("mechanic_kind")
            for k, v in mechanic_meta.items():
                if k not in ("mechanic_kind",):
                    patch[k] = v
        # Caller will merge lists; we emit append-style payload. apply_delta merges by node_id.
        delta = GraphDelta(
            node_updates=[(canonical_id, patch)],
        )
        return canonical_id, delta, False


# -----------------------------------------------------------------------------
# Graph type and core helpers
# -----------------------------------------------------------------------------


@dataclass
class Graph:
    """Simple node/edge graph for RAG queries. node_index maps node id -> index for O(1) patch."""

    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    node_index: Dict[str, int] = field(default_factory=dict)

    def add_node(self, node_id: str, node_type: str, payload: Dict[str, Any]) -> None:
        self.nodes.append({"id": node_id, "type": node_type, **payload})
        self.node_index[node_id] = len(self.nodes) - 1

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        edge_payload = {"source": source, "target": target, "relation": relation}
        if payload:
            edge_payload.update(payload)
        self.edges.append(edge_payload)

    def to_dict(self) -> Dict[str, Any]:
        payload = {"nodes": self.nodes, "edges": self.edges}
        if self.stats:
            payload["stats"] = self.stats
        return payload


def graph_from_payload(payload: Dict[str, Any]) -> Graph:
    """Build a Graph from a dict with 'nodes' and 'edges' (e.g. loaded merged.graph.json).
    Rebuilds node_index for O(1) patch. Use as chunk_graph_payload in build_fact_graph to
    add the fact layer on top of a disk graph."""
    nodes = list(payload.get("nodes") or [])
    edges = list(payload.get("edges") or [])
    stats = dict(payload.get("stats") or {})
    node_index: Dict[str, int] = {}
    for i, node in enumerate(nodes):
        nid = node.get("id")
        if nid is not None:
            node_index[nid] = i
    return Graph(nodes=nodes, edges=edges, stats=stats, node_index=node_index)


def _normalize_entity_name(text: str) -> str:
    cleaned = normalize_space(text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("*", "")
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9\s'\-]", " ", cleaned)
    cleaned = normalize_space(cleaned)
    return cleaned


def _normalize_entity_key(text: str) -> str:
    normalized = _normalize_entity_name(text)
    return normalized.lower()


def _sort_ownership_candidates(
    candidate_ids: List[str],
    entity_type_by_id: Dict[str, str],
    entity_name_by_id: Dict[str, str],
) -> List[str]:
    return sorted(
        candidate_ids,
        key=lambda candidate: (
            MECHANIC_FRAME_TYPE_PRIORITY.index(entity_type_by_id.get(candidate, ""))
            if entity_type_by_id.get(candidate) in MECHANIC_FRAME_TYPES
            else len(MECHANIC_FRAME_TYPE_PRIORITY),
            _normalize_entity_key(entity_name_by_id.get(candidate, "")),
            candidate,
        ),
    )


def _slugify_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


STRUCTURAL_HEADER_TERMS = {
    "level",
    "levels",
    "class",
    "classes",
    "ancestry",
    "ancestries",
    "background",
    "backgrounds",
    "feat",
    "feats",
    "spell",
    "spells",
    "equipment",
    "item",
    "items",
    "weapon",
    "weapons",
    "armor",
    "traits",
    "skills",
    "skill",
}

ROLE_TAG_KEYWORDS = {
    "ancestry",
    "class",
    "archetype",
    "background",
    "heritage",
    "race",
    "species",
    "subclass",
    "trait",
    "role",
}

BEHAVIORAL_CONTENT_KINDS = {
    "feat",
    "spell",
    "rule",
    "action",
    "ability",
    "item",
    "equipment",
    "weapon",
    "armor",
}


def _is_level_like(name_key: str) -> bool:
    if not name_key:
        return False
    if name_key == "level":
        return True
    return bool(re.match(r"^\d+(st|nd|rd|th)\s+level$", name_key))


def _classify_mechanic_kind(
    name: str,
    *,
    entity_type: Optional[str] = None,
    content_kind: Optional[str] = None,
    block_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, object]:
    normalized = _normalize_entity_key(name)
    content_kind = (content_kind or "").lower()
    block_type = (block_type or "").lower()
    tags = [tag.lower() for tag in (tags or []) if tag]

    if entity_type in {"Spell", "Feat", "Rule", "Action", "Ability", "Item"}:
        return {
            "mechanic_kind": "behavioral",
            "expects_facts": True,
            "retrieval_target": True,
        }

    if content_kind in BEHAVIORAL_CONTENT_KINDS:
        return {
            "mechanic_kind": "behavioral",
            "expects_facts": True,
            "retrieval_target": True,
        }

    if _is_level_like(normalized):
        return {
            "mechanic_kind": "structural",
            "expects_facts": False,
            "retrieval_target": False,
        }

    if any(keyword in tag for tag in tags for keyword in ROLE_TAG_KEYWORDS):
        return {
            "mechanic_kind": "taxonomic",
            "expects_facts": False,
            "retrieval_target": False,
        }

    if block_type in {"sectionheader", "title"} and normalized in STRUCTURAL_HEADER_TERMS:
        return {
            "mechanic_kind": "structural",
            "expects_facts": False,
            "retrieval_target": False,
        }

    if normalized in STRUCTURAL_HEADER_TERMS:
        return {
            "mechanic_kind": "structural",
            "expects_facts": False,
            "retrieval_target": False,
        }

    return {
        "mechanic_kind": "behavioral",
        "expects_facts": True,
        "retrieval_target": True,
    }


def _normalize_book_id(document_id: str) -> str:
    if not document_id:
        return "unknown"
    match = re.match(r"^(.*?)(?:-\d{3}-\d{3}|-\d{3})$", document_id)
    if match:
        return match.group(1)
    return document_id


# Document ID prefix → global ruleset ID (canon namespace). Longest match first.
# Used when ruleset_id is not passed so entity IDs align with benchmark/vocabulary (canon:{ruleset}:...).
_DOCUMENT_PREFIX_TO_RULESET: List[Tuple[str, str]] = [
    ("sf2e-playercore", "starfinder2e"),
    ("sf2e-gmcore", "starfinder2e"),
    ("sf2e-aliencore", "starfinder2e"),
    ("sf2e-galaxyguide", "starfinder2e"),
    ("sf2e-", "starfinder2e"),
    ("starfinder", "starfinder2e"),
    ("pathfinder2e-", "pathfinder2e"),
    ("pf2e-", "pathfinder2e"),
    ("pathfinder2e", "pathfinder2e"),
    ("pf2e", "pathfinder2e"),
]


def infer_ruleset_from_document_id(document_id: str) -> Optional[str]:
    """Infer global ruleset ID from document ID for canon:{ruleset}:{type}:{slug} entity IDs.
    Returns None if no mapping; caller should fall back to doc_id or require explicit ruleset_id."""
    if not document_id:
        return None
    lower = document_id.lower()
    for prefix, ruleset in _DOCUMENT_PREFIX_TO_RULESET:
        if lower.startswith(prefix):
            return ruleset
    return None


def _derive_chapter_id(book_id: str, section_path: List[str]) -> Optional[str]:
    if not section_path:
        return None
    chapter_title = section_path[0]
    chapter_slug = _slugify_name(chapter_title)
    if not chapter_slug:
        return None
    return f"chapter:{book_id}:{chapter_slug}"


def _canonical_entity_id(ruleset_id: str, entity_type: str, name: str, fallback_key: str) -> str:
    ruleset_slug = _slugify_name(ruleset_id) or "unknown"
    name_slug = _slugify_name(name)
    if not name_slug:
        name_slug = hashlib.sha1(fallback_key.encode("utf-8")).hexdigest()[:12]
    return f"canon:{ruleset_slug}:{entity_type.lower()}:{name_slug}"


def _is_canonical_id(value: str) -> bool:
    return isinstance(value, str) and value.startswith("canon:")


def audit_entity_namespace(
    nodes: List[Dict[str, Any]],
    expected_ruleset_id: Optional[str] = None,
) -> None:
    """Fail fast if entity IDs use more than one canon namespace or do not match expected.

    Entity IDs use the form canon:{namespace}:{type}:{slug}. This audit ensures a single
    namespace for benchmark comparability and optional match to expected_ruleset_id
    (compared after slugifying).

    Raises:
        ValueError: If more than one namespace appears, or expected_ruleset_id is set
            and the single namespace does not match its slugified form.
    """
    namespaces: Set[str] = set()
    for node in nodes:
        nid = node.get("id") if isinstance(node, dict) else None
        if not isinstance(nid, str) or not nid.startswith("canon:"):
            continue
        parts = nid.split(":", 3)
        if len(parts) >= 2 and parts[1]:
            namespaces.add(parts[1])
    if not namespaces:
        return
    if len(namespaces) > 1:
        raise ValueError(
            f"Entity ID namespace drift: more than one canon namespace in graph: {sorted(namespaces)}. "
            "Use a single ruleset_id for benchmarking."
        )
    if expected_ruleset_id is not None:
        expected_slug = _slugify_name(expected_ruleset_id)
        (actual,) = namespaces
        if actual != expected_slug:
            raise ValueError(
                f"Entity ID namespace mismatch: expected canon:{expected_slug}:* "
                f"but graph has canon:{actual}:*. Pass ruleset_id={expected_ruleset_id!r} when building."
            )


def _is_abbreviation(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2,10}[0-9]?", token or ""))


def _is_reasonable_canonical(name: str) -> bool:
    if not name:
        return False
    if len(name) < 4:
        return False
    return bool(re.search(r"[A-Za-z]", name))


def _extract_alias_pairs(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []
    patterns = [
        re.compile(r"\b([A-Z][A-Za-z0-9\s'\-]{3,80})\s*\(\s*([A-Z]{2,10}[0-9]?)\s*\)"),
        re.compile(r"\b([A-Z]{2,10}[0-9]?)\s*\(\s*([A-Z][A-Za-z0-9\s'\-]{3,80})\s*\)"),
    ]
    pairs: List[Tuple[str, str]] = []
    for pattern in patterns:
        for match in pattern.findall(text):
            left, right = match[0].strip(), match[1].strip()
            if _is_abbreviation(left) and not _is_abbreviation(right):
                pairs.append((left, right))
            elif _is_abbreviation(right) and not _is_abbreviation(left):
                pairs.append((right, left))
    return pairs


def _merge_alias_map(base: Dict[str, str], additions: Dict[str, str]) -> Dict[str, str]:
    for alias, canonical in additions.items():
        if alias and canonical and alias != canonical:
            base.setdefault(alias, canonical)
    return base


def _build_entity_alias_map(
    chunks: List[EnrichedChunk], resolved_config: Optional[Any]
) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    deterministic_rules = (resolved_config.deterministic_rules or {}) if resolved_config else {}
    config_aliases = deterministic_rules.get("entity_aliases", {})

    if isinstance(config_aliases, dict):
        for alias, canonical in config_aliases.items():
            alias_key = _normalize_entity_key(str(alias))
            canonical_norm = _normalize_entity_name(str(canonical))
            if alias_key and canonical_norm:
                alias_map[alias_key] = canonical_norm
    elif isinstance(config_aliases, list):
        for entry in config_aliases:
            if not isinstance(entry, dict):
                continue
            alias = _normalize_entity_key(str(entry.get("alias", "")))
            canonical = _normalize_entity_name(str(entry.get("canonical", "")))
            if alias and canonical:
                alias_map[alias] = canonical

    derived_aliases: Dict[str, str] = {}
    for chunk in chunks:
        for alias_raw, canonical_raw in _extract_alias_pairs(chunk.text):
            alias_norm = _normalize_entity_key(alias_raw)
            canonical_norm = _normalize_entity_name(canonical_raw)
            if not _is_reasonable_canonical(canonical_norm):
                continue
            if alias_norm and canonical_norm and alias_norm != canonical_norm:
                derived_aliases[alias_norm] = canonical_norm

    return _merge_alias_map(alias_map, derived_aliases)


def _resolve_alias_name(name: str, alias_map: Dict[str, str]) -> Tuple[str, Optional[str]]:
    normalized = _normalize_entity_key(name)
    if not normalized:
        return "", None
    canonical = alias_map.get(normalized)
    if canonical and canonical != normalized:
        return canonical, _normalize_entity_name(name)
    return name, None


def _extract_entity_name(chunk: EnrichedChunk) -> str:
    if chunk.content_kind == "spell":
        title = extract_spell_title_from_text(chunk.text)
        return _normalize_entity_name(title or "")
    if chunk.content_kind == "feat":
        title = extract_feat_title_from_text(chunk.text)
        return _normalize_entity_name(title or "")
    if chunk.content_kind == "rule":
        if chunk.block_type in {"SectionHeader", "Title"}:
            if chunk.section_path:
                return _normalize_entity_name(chunk.section_path[-1])
            first_line = (chunk.text or "").splitlines()[0] if chunk.text else ""
            return _normalize_entity_name(first_line[:120])
        return ""
    if chunk.section_path:
        return _normalize_entity_name(chunk.section_path[-1])
    first_line = (chunk.text or "").splitlines()[0] if chunk.text else ""
    return _normalize_entity_name(first_line[:120])


SECTION_ENTITY_KEYWORDS = {
    "conditions": "Condition",
    "condition": "Condition",
    "classes": "Class",
    "class": "Class",
    "ancestries": "Ancestry",
    "ancestry": "Ancestry",
    "backgrounds": "Background",
    "background": "Background",
    "monsters": "Monster",
    "bestiary": "Monster",
}

RELATION_PATTERNS = [
    ("requires", re.compile(r"\brequires?\s+\*\*([A-Z][A-Za-z0-9\s'\-]{2,80})\*\*", re.IGNORECASE)),
    ("requires", re.compile(r"\brequires?\s+([A-Z][A-Za-z0-9\s'\-]{2,80})(?=[\.,;:\n])")),
    ("grants", re.compile(r"\bgrants?\s+\*\*([A-Z][A-Za-z0-9\s'\-]{2,80})\*\*", re.IGNORECASE)),
    ("grants", re.compile(r"\bgrants?\s+([A-Z][A-Za-z0-9\s'\-]{2,80})(?=[\.,;:\n])")),
    ("affects", re.compile(r"\baffects?\s+\*\*([A-Z][A-Za-z0-9\s'\-]{2,80})\*\*", re.IGNORECASE)),
    ("affects", re.compile(r"\baffects?\s+([A-Z][A-Za-z0-9\s'\-]{2,80})(?=[\.,;:\n])")),
    ("has_effect", re.compile(r"\bhas effect(?:s)?\s+(?:of\s+)?\*\*([A-Z][A-Za-z0-9\s'\-]{2,80})\*\*", re.IGNORECASE)),
    ("has_effect", re.compile(r"\bhas effect(?:s)?\s+(?:of\s+)?([A-Z][A-Za-z0-9\s'\-]{2,80})(?=[\.,;:\n])")),
]

RELATION_TARGET_LIMIT = 4
CHUNK_ADJACENCY_LIMIT = 12
MECHANIC_FRAME_TYPES = {"MechanicFrame", "Spell", "Feat", "Rule", "Action", "Ability"}
MECHANIC_FRAME_TYPE_PRIORITY = ["MechanicFrame", "Spell", "Feat", "Rule", "Action", "Ability"]
STRUCTURAL_COREFERENCE_RELATION = "structural_coreference"

# Node kinds per ENTITY_FACT_PARTITION_INVARIANTS.md
STRUCTURAL_NODE_TYPES = {"document", "section", "chunk"}
FACT_NODE_TYPES = {"RuleFact"}


class NodeKind(str, Enum):
    """Node kind partition: structural | entity | fact. Facts are not entities."""

    STRUCTURAL = "structural"
    ENTITY = "entity"
    FACT = "fact"


def get_node_kind(node: Dict[str, Any]) -> NodeKind:
    """Classify node by type. Entity-ness is explicit, not derived by exclusion."""
    t = node.get("type") or ""
    if t in STRUCTURAL_NODE_TYPES:
        return NodeKind.STRUCTURAL
    if t in FACT_NODE_TYPES:
        return NodeKind.FACT
    return NodeKind.ENTITY


def is_entity_like(node: Dict[str, Any]) -> bool:
    """True only for entity nodes (not structural, not fact). Use for counts, alias maps, traversal purity."""
    return get_node_kind(node) == NodeKind.ENTITY
# CandidateKind -> relation name for has_* edges from primary entity to trait/tradition/rank/tag/stat
HAS_RELATION_BY_KIND: Dict[CandidateKind, str] = {
    CandidateKind.TRAIT: "has_trait",
    CandidateKind.TRADITION: "has_tradition",
    CandidateKind.SPELL_RANK: "has_rank",
    CandidateKind.TAG: "has_tag",
    CandidateKind.SPELL_STAT: "has_stat",
}
CORE_ENTITY_TYPES = {
    "Spell",
    "Feat",
    "Item",
    "Rule",
    "Condition",
    "Class",
    "Ancestry",
    "Background",
    "Monster",
}

PROCEDURE_ANCHOR_MAP: Dict[str, List[Tuple[str, List[str], List[str]]]] = {
    "procedure:gain_dying": [
        ("results_in", ["Condition", "MechanicFrame"], ["dying"]),
    ],
    "procedure:dying": [
        ("results_in", ["Condition", "MechanicFrame"], ["dying"]),
    ],
    "procedure:knocked_out_transition": [
        ("results_in", ["Condition", "MechanicFrame"], ["unconscious"]),
    ],
    "procedure:persistent_damage_tick": [
        ("results_in", ["Condition", "MechanicFrame"], ["persistent damage"]),
    ],
    "procedure:roll_strike": [
        ("affects", ["MechanicFrame", "Action"], ["strike", "attack"]),
    ],
    "procedure:attack_resolution": [
        ("part_of", ["MechanicFrame", "Action"], ["attack", "strike"]),
    ],
    "procedure:miss_resolution": [
        ("branches_from", ["MechanicFrame", "Action"], ["attack", "strike"]),
    ],
    "procedure:critical_resolution": [
        ("branches_from", ["MechanicFrame", "Action"], ["attack", "strike"]),
    ],
    "procedure:damage_roll": [
        ("part_of", ["MechanicFrame", "Action"], ["damage"]),
    ],
    "procedure:apply_damage": [
        ("affects", ["MechanicFrame", "Action"], ["damage"]),
    ],
    "procedure:perception_check": [
        ("affects", ["MechanicFrame", "Action"], ["perception"]),
    ],
    "procedure:initiative_roll": [
        ("affects", ["MechanicFrame", "Action"], ["initiative"]),
    ],
    "procedure:movement": [
        ("affects", ["MechanicFrame", "Action"], ["movement"]),
    ],
}

# Only add steps for procedures with observed overrides in audits.
PROCEDURE_STEP_PATTERNS: Dict[str, List[Tuple[str, Pattern[str]]]] = {
    "procedure:attack_resolution": [
        (
            "damage_roll",
            re.compile(
                r"\bnormal weapon damage dice\b|\bdamage dice\b|\bextra damage\b|\bdamage instead of\b",
                re.IGNORECASE,
            ),
        ),
        (
            "critical_resolution",
            re.compile(r"\bcritical\s+(hit|success|failure)\b|\bon a critical\b", re.IGNORECASE),
        ),
        ("miss_resolution", re.compile(r"\bon a miss\b|\bmiss(?:es|ed)?\b|\battack misses\b", re.IGNORECASE)),
        (
            "hit_resolution",
            re.compile(r"\bon a hit\b|\bif the attack hits\b|\bon a successful hit\b", re.IGNORECASE),
        ),
        ("attack_roll", re.compile(r"\battack roll\b|\broll(?:ing)?\s+(?:to\s+)?strike\b", re.IGNORECASE)),
    ],
    "procedure:apply_damage": [
        (
            "damage_roll",
            re.compile(
                r"\bnormal damage\b|\bdamage dice\b|\bdamage instead of\b|\bextra damage\b|\badditional damage\b",
                re.IGNORECASE,
            ),
        ),
        (
            "damage_type_assignment",
            re.compile(
                r"\b(type|types)\s+of\s+damage\b|\b(fire|cold|electricity|acid|poison|sonic|force|precision)\s+damage\b",
                re.IGNORECASE,
            ),
        ),
        (
            "damage_scaling",
            re.compile(
                r"\bdouble damage\b|\bhalf damage\b|\bincrease(?:s|d)? damage\b|\breduce(?:s|d)? damage\b|\bdamage scales\b",
                re.IGNORECASE,
            ),
        ),
    ],
    "procedure:dying": [
        ("recovery_check", re.compile(r"\brecovery check(s)?\b", re.IGNORECASE)),
        (
            "gain_dying",
            re.compile(
                r"\bgain(?:s|ed|ing)?\s+dying\b|\bbecome(?:s)?\s+dying\b|\bdying condition\b",
                re.IGNORECASE,
            ),
        ),
        (
            "increase_dying",
            re.compile(
                r"\bincrease(?:s|d|ing)?\s+your\s+dying\b|\bdying\s+value\b",
                re.IGNORECASE,
            ),
        ),
        (
            "stabilize",
            re.compile(r"\bstabiliz(?:e|es|ed|ing)\b|\bstable at 0\b", re.IGNORECASE),
        ),
    ],
    "procedure:movement": [
        ("movement_action", re.compile(r"\bwhen you move\b|\bwhile moving\b", re.IGNORECASE)),
        ("leaving_square", re.compile(r"\bleav(?:e|es|ing)\s+(?:a|the)\s+square\b", re.IGNORECASE)),
        ("provokes_reaction", re.compile(r"\bprovok(?:e|es|ing)\b", re.IGNORECASE)),
    ],
}


def _normalize_step_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower())
    cleaned = cleaned.strip("_")
    return cleaned


def _derive_procedure_step_id(procedure_id: str, clause_text: Optional[str]) -> Optional[str]:
    if not procedure_id or not clause_text:
        return None
    patterns = PROCEDURE_STEP_PATTERNS.get(procedure_id, [])
    if not patterns:
        return None
    for step_slug, pattern in patterns:
        if pattern.search(clause_text):
            normalized = _normalize_step_slug(step_slug)
            if normalized:
                return f"{procedure_id}#step:{normalized}"
    return None


def _extract_dying_threshold_override(text: Optional[str]) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    normalized = str(text).lower()
    if "instead of" not in normalized:
        return None
    values = [int(value) for value in re.findall(r"\bdying\s+(\d+)\b", normalized)]
    if len(values) < 2:
        return None
    return values[0], values[1]


def _strip_markdown_title(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = normalize_space(cleaned)
    return cleaned


def _extract_bold_title(text: str) -> str:
    match = re.match(r"^\s*\*\*(.+?)\*\*", text or "")
    if not match:
        return ""
    return _normalize_entity_name(match.group(1))


def _infer_section_entity_type(chunk: EnrichedChunk) -> Optional[str]:
    if chunk.block_type not in {"SectionHeader", "Title"}:
        return None
    for segment in chunk.section_path:
        segment_lower = segment.lower()
        for keyword, entity_type in SECTION_ENTITY_KEYWORDS.items():
            if keyword in segment_lower:
                return entity_type
    return None


def _infer_entity_type_from_header_text(text: str) -> Optional[str]:
    normalized = _normalize_entity_name(_strip_markdown_title(text)).lower()
    if not normalized:
        return None
    if normalized in SECTION_ENTITY_KEYWORDS:
        return SECTION_ENTITY_KEYWORDS[normalized]
    if normalized.startswith("chapter ") or normalized.startswith("part "):
        for keyword, entity_type in SECTION_ENTITY_KEYWORDS.items():
            if keyword in normalized:
                return entity_type
    return None


def _extract_section_entity_name(chunk: EnrichedChunk) -> str:
    if not chunk.section_path:
        return _normalize_entity_name(_strip_markdown_title(chunk.text))
    last_segment = chunk.section_path[-1]
    last_lower = last_segment.lower()
    if any(keyword in last_lower for keyword in SECTION_ENTITY_KEYWORDS):
        if len(chunk.section_path) > 1:
            return _normalize_entity_name(chunk.section_path[-2])
        return _normalize_entity_name(_strip_markdown_title(chunk.text))
    return _normalize_entity_name(last_segment)


def _infer_tag_entity_type(chunk: EnrichedChunk) -> Optional[str]:
    if not chunk.tags:
        return None
    for tag in chunk.tags:
        tag_lower = tag.lower()
        entity_type = SECTION_ENTITY_KEYWORDS.get(tag_lower)
        if entity_type:
            return entity_type
    return None


# Category keywords to filter out when extracting specific entity names
_PATH_CATEGORY_KEYWORDS = {
    "ancestries", "ancestry", "classes", "class",
    "backgrounds", "background", "chapter", "appendix",
    "versatile heritages", "mixed ancestries", "heritages",
    "conditions", "condition", "monsters", "bestiary",
    "feats", "spells", "items", "equipment", "gear",
    "skills", "actions", "activities", "traits",
}

# Keywords that indicate a SectionHeader is a category header, not an entity name
_CATEGORY_HEADER_KEYWORDS = {
    # Category headers
    "ancestries", "ancestry", "classes", "class", "backgrounds", "background",
    "feats", "spells", "equipment", "gear", "skills", "actions",
    "chapter", "appendix", "heritages", "heritage", "conditions",
    "introduction", "overview", "appendix", "index", "glossary",
    # Level headers
    "level", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th",
    # Attribute/stat headers
    "attribute", "boosts", "flaw", "languages", "traits", "physical description",
    "hit points", "proficiencies", "perception", "saving throws", "defenses",
    "key attribute", "class dc", "initial", "armor", "attacks", "weapons", "size", "speed",
    # Social/descriptive headers
    "society", "beliefs", "sample names", "sample character", "playing", "others probably",
    "you might", "key terms", "prerequisites", "faith", "allies", "your allies",
    "character sheet", "port of call", "home world", "deity", "age", "gender",
    # Credits/metadata
    "authors", "author", "editing", "editor", "editors", "development",
    "artist", "artists", "art direction", "graphic design", "publisher",
    "creative", "manager", "special thanks", "based on",
    # Generic document structure
    "example", "examples", "overview", "summary", "using", "format",
    "reading", "step", "during", "while", "in downtime", "encounters",
    "exploration", "combat", "social", "downtime",
    # Game mechanics
    "hero points", "bulk", "currency", "rarity", "round", "turn",
    "perception", "proficiency", "dice", "gaming", "tools of play",
    "basics", "rules", "advancement", "multiclass", "dedication",
    # Feature header fields
    "trigger", "effect", "effects", "requirements", "frequency", "cost", "duration",
    "benefit", "special", "access", "source",
    # Other noise patterns
    "the first", "the players", "the game", "the galaxy", "player core", "starfinder", "versatile",
    "cover", "interior", "devotee benefits", "archetypes", "archetype",
    "spell repertoire", "cantrips", "heightening", "swapping",
}


def _extract_named_entity_from_path(
    chunk: EnrichedChunk,
    entity_type: str
) -> Optional[str]:
    """
    Extract specific entity name from section path.
    
    For a chunk with section_path = ["Chapter 2", "Ancestries", "Example"]
    and entity_type = "Ancestry", returns "Example".
    
    Filters out:
    - Category keywords ("ancestries", "classes", etc.)
    - Chapter headers ("chapter N ...")
    - Generic subsections
    """
    if not chunk.section_path:
        return None
    
    # Walk section_path from end to find specific entity name
    for segment in reversed(chunk.section_path):
        segment_lower = segment.lower().strip()
        
        # Skip empty segments
        if not segment_lower:
            continue
        
        # Skip category keywords
        if any(kw in segment_lower for kw in _PATH_CATEGORY_KEYWORDS):
            continue
        
        # Skip chapter/appendix headers (e.g., "Chapter 2", "Chapter 3 Classes")
        if segment_lower.startswith("chapter ") or segment_lower.startswith("appendix "):
            continue
        
        # Skip very short names (likely abbreviations or noise)
        if len(segment_lower) < 3:
            continue
        
        # Found a specific name
        return _normalize_entity_name(segment)
    
    return None


def _infer_entity_type_from_section_path(
    section_str: str, is_rule_bearing: bool
) -> str:
    """Infer entity type from full section path (for header-scope propagation)."""
    section_lower = section_str.lower()
    if "spell" in section_lower:
        return "Spell"
    if "feat" in section_lower:
        return "Feat"
    if "ancestr" in section_lower or "heritage" in section_lower:
        return "Ancestry"
    if "class" in section_lower and "subclass" not in section_lower:
        return "Class"
    if "background" in section_lower:
        return "Background"
    if "condition" in section_lower:
        return "Condition"
    if "action" in section_lower:
        return "Action"
    if "equipment" in section_lower or "item" in section_lower or "gear" in section_lower:
        return "Item"
    if "monster" in section_lower or "bestiary" in section_lower:
        return "Monster"
    if is_rule_bearing:
        return "MechanicFrame"
    return "Rule"


def _extract_header_scope_entity(chunk: EnrichedChunk) -> Optional[Tuple[str, str]]:
    """
    Extract entity (name, type) from section path when chunk has no explicit entity.

    Walks section_path from most specific (last segment) to least, skipping
    structural/category headers. Used as fallback so chunks under a specific
    header (e.g. "Lashunta > Feats > Telepathic Bond") get a describing entity
    even without an explicit header in the chunk text.
    """
    if not chunk.section_path:
        return None
    section_str = " ".join(chunk.section_path).lower()
    for segment in reversed(chunk.section_path):
        normalized = _normalize_entity_name(segment)
        if not normalized or len(normalized) < 3:
            continue
        segment_lower = normalized.lower()
        if segment_lower in _PATH_CATEGORY_KEYWORDS:
            continue
        if segment_lower.startswith("chapter ") or segment_lower.startswith("appendix "):
            continue
        if not _is_simple_entity_name(segment):
            continue
        entity_type = _infer_entity_type_from_section_path(
            section_str, chunk.is_rule_bearing
        )
        return (normalized, entity_type)
    return None


def _has_entity_signature(
    chunks: List[EnrichedChunk],
    chunk_idx: int,
    entity_type: str,
    window_size: int = 20,
) -> bool:
    """Check nearby headers for ancestry/class signature fields."""
    if entity_type not in {"Ancestry", "Class"}:
        return True

    signature_map = {
        "Ancestry": {"attribute boosts", "hit points", "size", "speed", "languages", "traits"},
        "Class": {"key attribute", "key attributes", "hit points", "initial proficiencies"},
    }
    threshold_map = {"Ancestry": 1, "Class": 2}
    signatures = signature_map.get(entity_type, set())
    threshold = threshold_map.get(entity_type, 2)
    hits = 0

    for neighbor in chunks[chunk_idx + 1 : chunk_idx + window_size]:
        if neighbor.block_type not in {"SectionHeader", "Title"}:
            continue
        header_raw = _strip_markdown_title(neighbor.text)
        header = _normalize_entity_name(header_raw).lower()
        if not header:
            continue
        if header in signatures:
            hits += 1
            if hits >= threshold:
                return True
        # Stop once we hit another entity-like header (likely next entry)
        if _is_simple_entity_name(header_raw):
            return False
    return False


def _has_rule_bearing_followup(
    chunks: List[EnrichedChunk],
    chunk_idx: int,
    window_size: int = 8,
) -> bool:
    """Check if a header is followed by rule-bearing content before next header."""
    for neighbor in chunks[chunk_idx + 1 : chunk_idx + window_size + 1]:
        if neighbor.block_type in {"SectionHeader", "Title"}:
            header_text = _strip_markdown_title(neighbor.text)
            if _is_simple_entity_name(header_text):
                return False
        if neighbor.is_rule_bearing:
            return True
    return False


def _should_inherit_mechanic_frame(chunk: EnrichedChunk) -> bool:
    if chunk.is_rule_bearing:
        return True
    if chunk.block_type in {"Text", "Table", "TableCell"}:
        return True
    if chunk.content_kind in {"rule", "feat", "spell", "item"}:
        return True
    return False


def _is_simple_entity_name(text: str) -> bool:
    """
    Check if text looks like a simple entity name (e.g., "EXAMPLE NAME").
    
    Returns True for simple names, False for category headers or complex text.
    """
    if not text:
        return False
    
    cleaned = text.strip().replace("*", "").replace("_", "").strip()
    cleaned_lower = cleaned.lower()
    
    # Skip empty or too short
    if len(cleaned) < 4:  # Most entity names are 4+ characters
        return False
    
    # Skip if it contains category keywords
    if any(kw in cleaned_lower for kw in _CATEGORY_HEADER_KEYWORDS):
        return False
    
    # Skip if it looks like a feat/spell (contains "FEAT", "SPELL", "[action]", etc.)
    if "feat" in cleaned_lower or "spell" in cleaned_lower:
        return False
    if "[" in cleaned or "]" in cleaned:  # Action markers
        return False
    
    # Skip if it's too long (probably a description, not a name)
    if len(cleaned) > 30:  # Entity names are typically short
        return False
    
    # Skip if it contains common non-name patterns
    if ":" in cleaned or "—" in cleaned or "..." in cleaned:
        return False
    
    # Skip generic game terms
    generic_terms = {
        "action", "attack", "check", "save", "skill", "speed", "trait",
        "bonuses", "penalties", "initiative", "modifier", "bonus", "penalty",
        "constitution", "strength", "dexterity", "intelligence", "wisdom", "charisma",
        "damage", "defense", "defenses", "resistance", "immunity", "vulnerable",
        "narrative", "characters", "defining", "creating", "exploring",
        "directive", "directives", "ability", "abilities", "power", "powers",
    }
    if cleaned_lower in generic_terms or any(term in cleaned_lower for term in generic_terms if len(term) > 5):
        return False
    
    # Accept if it's 1-2 words (ancestry/class names are typically 1-2 words)
    words = cleaned.split()
    if len(words) > 2:
        return False
    
    # Must start with capital letter (proper noun pattern)
    if not cleaned[0].isupper():
        return False
    
    return True


def _build_entity_type_context(
    chunks: List[EnrichedChunk],
    window_size: int = 30
) -> Dict[int, str]:
    """
    Build a mapping from chunk index to inferred entity type context.
    
    Uses nearby tags within a window to infer context.
    
    Returns dict mapping chunk_index -> entity_type (e.g., "Ancestry", "Class")
    """
    context_map: Dict[int, str] = {}
    
    # First, identify chunks with relevant tags for fallback
    tagged_indices: Dict[int, str] = {}
    for i, chunk in enumerate(chunks):
        if not chunk.tags:
            continue
        for tag in chunk.tags:
            tag_lower = tag.lower()
            if "ancestr" in tag_lower or "heritage" in tag_lower:
                tagged_indices[i] = "Ancestry"
                break
            elif "class" in tag_lower and "subclass" not in tag_lower:
                tagged_indices[i] = "Class"
                break
            elif "background" in tag_lower:
                tagged_indices[i] = "Background"
                break
    
    # Build context from explicit chapter/category headers
    current_context: Optional[str] = None
    for i, chunk in enumerate(chunks):
        if chunk.block_type != "SectionHeader":
            continue

        header_context = _infer_entity_type_from_header_text(chunk.text or "")
        if header_context:
            current_context = header_context
            continue

        if current_context:
            context_map[i] = current_context

    # Backfill context from nearby tags within window
    for i, chunk in enumerate(chunks):
        if chunk.block_type != "SectionHeader":
            continue
        if i in context_map:
            continue
        for j in range(max(0, i - window_size), min(len(chunks), i + window_size)):
            if j in tagged_indices:
                context_map[i] = tagged_indices[j]
                break
    
    return context_map


def _extract_tag_entity_name(chunk: EnrichedChunk) -> str:
    title = _extract_bold_title(chunk.text or "")
    if title:
        return title
    if chunk.block_type not in {"SectionHeader", "Title"}:
        return ""
    return _normalize_entity_name(_strip_markdown_title(chunk.text))


def _extract_relation_mentions(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []
    mentions: List[Tuple[str, str]] = []
    for relation, pattern in RELATION_PATTERNS:
        for match in pattern.findall(text):
            raw = match if isinstance(match, str) else match[0]
            target = _normalize_entity_name(raw)
            if target:
                mentions.append((relation, target))
                if len([m for m in mentions if m[0] == relation]) >= RELATION_TARGET_LIMIT:
                    break
    return mentions


def _add_entity_index(
    index: Dict[str, str],
    canonical_id: str,
    names: List[str],
) -> None:
    for name in names:
        canonical_key = _normalize_entity_key(name)
        if not canonical_key:
            continue
        index.setdefault(canonical_key, canonical_id)


def _select_mechanic_frame_id(
    name_key: str,
    mechanic_frame_ids_by_key: Dict[str, List[str]],
    entity_type_by_id: Dict[str, str],
) -> Optional[str]:
    if not name_key:
        return None
    candidates = mechanic_frame_ids_by_key.get(name_key) or []
    if not candidates:
        return None
    candidates.sort(
        key=lambda candidate: (
            MECHANIC_FRAME_TYPE_PRIORITY.index(entity_type_by_id.get(candidate, ""))
            if entity_type_by_id.get(candidate) in MECHANIC_FRAME_TYPES
            else len(MECHANIC_FRAME_TYPE_PRIORITY),
            candidate,
        )
    )
    return candidates[0]


def _add_mechanic_frame_relations(
    graph: Graph,
    facts: List["RuleFact"],
    clause_mechanic_keys: Dict[str, Set[str]],
    entity_name_by_id: Dict[str, str],
    entity_type_by_id: Dict[str, str],
    fact_owner_by_id: Dict[str, str],
    fact_chunk_by_id: Dict[str, str],
    doc_id: str,
    enrichment_variant: Optional[str] = None,
) -> int:
    from .rule_facts import FactType

    mechanic_frame_ids_by_key: Dict[str, List[str]] = {}
    for entity_id, entity_type in entity_type_by_id.items():
        if entity_type not in MECHANIC_FRAME_TYPES:
            continue
        name = entity_name_by_id.get(entity_id, "")
        name_key = _normalize_entity_key(name)
        if name_key:
            mechanic_frame_ids_by_key.setdefault(name_key, []).append(entity_id)

    if not mechanic_frame_ids_by_key:
        return 0

    added = 0
    seen: Set[Tuple[str, str, str]] = set()
    strong_links: Set[Tuple[str, str]] = set()

    def _add_relation(source_id: str, target_id: str, relation: str, fact: "RuleFact") -> None:
        nonlocal added
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id, relation)
        if key in seen:
            return
        chunk_id = fact_chunk_by_id.get(fact.fact_id, "")
        graph.add_edge(
            source_id,
            target_id,
            relation,
            {
                "source_document": doc_id,
                "source_chunk_id": chunk_id,
                "clause_id": fact.clause_id,
                "fact_id": fact.fact_id,
                "fact_type": fact.fact_type.value,
                "extraction_method": "mechanic_relation",
            },
        )
        seen.add(key)
        added += 1

    for fact in facts:
        source_id = fact_owner_by_id.get(fact.fact_id)
        if not source_id:
            continue
        source_key = _normalize_entity_key(entity_name_by_id.get(source_id, ""))
        if not source_key:
            continue

        if fact.fact_type == FactType.REQUIRES and fact.object:
            target_key = _normalize_entity_key(fact.object)
            target_id = _select_mechanic_frame_id(target_key, mechanic_frame_ids_by_key, entity_type_by_id)
            if target_id:
                _add_relation(source_id, target_id, "requires_mechanic", fact)
                strong_links.add((source_id, target_id))

        if fact.fact_type in {FactType.MODIFIES, FactType.OVERRIDES, FactType.INSTEAD_OF, FactType.PREVENTS}:
            target_key = _normalize_entity_key(fact.object or "")
            target_id = _select_mechanic_frame_id(target_key, mechanic_frame_ids_by_key, entity_type_by_id)
            if target_id:
                _add_relation(source_id, target_id, "modifies_mechanic", fact)
                strong_links.add((source_id, target_id))
                if enrichment_variant == "E4":
                    rel = "overrides" if fact.fact_type in {FactType.OVERRIDES, FactType.INSTEAD_OF, FactType.PREVENTS} else "modifies"
                    _add_relation(source_id, target_id, rel, fact)

        if fact.override_target:
            target_key = _normalize_entity_key(fact.override_target)
            target_id = _select_mechanic_frame_id(target_key, mechanic_frame_ids_by_key, entity_type_by_id)
            if target_id:
                _add_relation(source_id, target_id, "modifies_mechanic", fact)
                strong_links.add((source_id, target_id))
                if enrichment_variant == "E4":
                    rel = "overrides" if fact.fact_type in {FactType.OVERRIDES, FactType.INSTEAD_OF, FactType.PREVENTS} else "modifies"
                    _add_relation(source_id, target_id, rel, fact)

        for mention_key in clause_mechanic_keys.get(fact.clause_id, set()):
            if mention_key == source_key:
                continue
            target_id = _select_mechanic_frame_id(
                mention_key, mechanic_frame_ids_by_key, entity_type_by_id
            )
            if not target_id:
                continue
            if (source_id, target_id) in strong_links:
                continue
            _add_relation(source_id, target_id, "references_mechanic", fact)

    return added


def _add_semantic_enrichment_edges(
    graph: Graph,
    enrichment_variant: Optional[str],
    doc_id: str,
    *,
    facts: Optional[List["RuleFact"]] = None,
    fact_owner_by_id: Optional[Dict[str, str]] = None,
    entity_name_by_id: Optional[Dict[str, str]] = None,
    entity_type_by_id: Optional[Dict[str, str]] = None,
    mechanic_frame_ids_by_key: Optional[Dict[str, List[str]]] = None,
    fact_chunk_by_id: Optional[Dict[str, str]] = None,
) -> int:
    """
    Add semantic edge enrichments per HANDOFF-Semantic-Edge-Enrichment-Under-Expressivity-Experiment.
    E1: precedes, follows between procedure steps (ordered by chunk/clause).
    E2: conditional edges (requires_condition, negated_by).
    E3: effect-target edges (affects_stat, affects_condition).
    """
    if not enrichment_variant or enrichment_variant not in {"E1", "E2", "E3", "E4"}:
        return 0
    if enrichment_variant == "E1":
        return _add_procedural_flow_edges(graph, doc_id)
    if enrichment_variant == "E2" and facts is not None and fact_owner_by_id is not None and mechanic_frame_ids_by_key is not None and entity_type_by_id is not None:
        return _add_conditional_edges_e2(
            graph=graph,
            doc_id=doc_id,
            facts=facts,
            fact_owner_by_id=fact_owner_by_id,
            entity_name_by_id=entity_name_by_id or {},
            entity_type_by_id=entity_type_by_id,
            mechanic_frame_ids_by_key=mechanic_frame_ids_by_key,
            fact_chunk_by_id=fact_chunk_by_id or {},
        )
    if enrichment_variant == "E3" and facts is not None and fact_owner_by_id is not None and mechanic_frame_ids_by_key is not None and entity_type_by_id is not None:
        return _add_effect_target_edges_e3(
            graph=graph,
            doc_id=doc_id,
            facts=facts,
            fact_owner_by_id=fact_owner_by_id,
            entity_name_by_id=entity_name_by_id or {},
            entity_type_by_id=entity_type_by_id,
            mechanic_frame_ids_by_key=mechanic_frame_ids_by_key,
            fact_chunk_by_id=fact_chunk_by_id or {},
        )
    return 0


def _add_procedural_flow_edges(graph: Graph, doc_id: str) -> int:
    """E1: Add precedes/follows between procedure steps (step_of → order by chunk/clause)."""
    from collections import defaultdict

    # step_of: source=step_id, target=procedure_id
    procedure_to_steps: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for edge in graph.edges:
        if edge.get("relation") != "step_of":
            continue
        step_id = edge.get("source", "")
        procedure_id = edge.get("target", "")
        if not step_id or not procedure_id:
            continue
        chunk_id = (edge.get("source_chunk_id") or "").strip()
        clause_id = (edge.get("clause_id") or "").strip()
        procedure_to_steps[procedure_id].append((step_id, chunk_id, clause_id))

    added = 0
    seen: Set[Tuple[str, str, str]] = set()
    for procedure_id, step_tuples in procedure_to_steps.items():
        if len(step_tuples) < 2:
            continue
        step_tuples.sort(key=lambda x: (x[1], x[2]))
        for i in range(len(step_tuples) - 1):
            step_a, chunk_a, clause_a = step_tuples[i]
            step_b, chunk_b, clause_b = step_tuples[i + 1]
            for (s1, s2, rel) in [(step_a, step_b, "precedes"), (step_b, step_a, "follows")]:
                key = (s1, s2, rel)
                if key in seen:
                    continue
                seen.add(key)
                graph.add_edge(
                    s1,
                    s2,
                    rel,
                    {
                        "source_document": doc_id,
                        "extraction_method": "procedure_flow_e1",
                    },
                )
                added += 1
    return added


def _add_conditional_edges_e2(
    graph: Graph,
    doc_id: str,
    facts: List["RuleFact"],
    fact_owner_by_id: Dict[str, str],
    entity_name_by_id: Dict[str, str],
    entity_type_by_id: Dict[str, str],
    mechanic_frame_ids_by_key: Dict[str, List[str]],
    fact_chunk_by_id: Dict[str, str],
) -> int:
    """E2: Add requires_condition and negated_by edges from UNLESS/REQUIRES/condition facts."""
    from .rule_facts import FactType

    added = 0
    seen: Set[Tuple[str, str, str]] = set()

    def _add_edge(source_id: str, target_id: str, relation: str, fact: "RuleFact") -> None:
        nonlocal added
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id, relation)
        if key in seen:
            return
        chunk_id = fact_chunk_by_id.get(fact.fact_id, "")
        graph.add_edge(
            source_id,
            target_id,
            relation,
            {
                "source_document": doc_id,
                "source_chunk_id": chunk_id,
                "clause_id": fact.clause_id,
                "fact_id": fact.fact_id,
                "extraction_method": "conditional_e2",
            },
        )
        seen.add(key)
        added += 1

    for fact in facts:
        source_id = fact_owner_by_id.get(fact.fact_id)
        if not source_id:
            continue

        # UNLESS: mechanic does not apply when condition/object holds → negated_by
        if fact.fact_type == FactType.UNLESS:
            for raw in (fact.object, fact.condition):
                if not raw:
                    continue
                target_key = _normalize_entity_key(raw)
                target_id = _select_mechanic_frame_id(
                    target_key, mechanic_frame_ids_by_key, entity_type_by_id
                )
                if target_id:
                    _add_edge(source_id, target_id, "negated_by", fact)

        # REQUIRES with condition-like object → requires_condition
        if fact.fact_type == FactType.REQUIRES and fact.object:
            target_key = _normalize_entity_key(fact.object)
            target_id = _select_mechanic_frame_id(
                target_key, mechanic_frame_ids_by_key, entity_type_by_id
            )
            if target_id:
                _add_edge(source_id, target_id, "requires_condition", fact)

        # fact.condition set (trigger condition) → requires_condition
        if fact.condition:
            target_key = _normalize_entity_key(fact.condition)
            target_id = _select_mechanic_frame_id(
                target_key, mechanic_frame_ids_by_key, entity_type_by_id
            )
            if target_id:
                _add_edge(source_id, target_id, "requires_condition", fact)

    return added


def _add_effect_target_edges_e3(
    graph: Graph,
    doc_id: str,
    facts: List["RuleFact"],
    fact_owner_by_id: Dict[str, str],
    entity_name_by_id: Dict[str, str],
    entity_type_by_id: Dict[str, str],
    mechanic_frame_ids_by_key: Dict[str, List[str]],
    fact_chunk_by_id: Dict[str, str],
) -> int:
    """E3: Add affects_stat and affects_condition edges from MODIFIES/OVERRIDES/TRIGGERS/PREVENTS facts."""
    from .rule_facts import FactType

    # Allowlists for stat vs condition classification (expanded for E3 recall)
    _STAT_TERMS = frozenset({
        "hit points", "hp", "ac", "armor class", "bonus", "penalty", "dying value",
        "wounded value", "doomed value", "damage", "persistent damage",
        "saving throw", "saving throws", "check", "checks", "dc", "modifier", "modifiers",
        "attack roll", "attack rolls", "damage roll", "damage dice", "die size",
        "resistance", "resistances", "immunity", "immunities", "weakness", "weaknesses",
        "speed", "movement", "multiple attack penalty", "map",
    })
    _CONDITION_TERMS = frozenset({
        "dying", "wounded", "doomed", "unconscious", "frightened", "persistent damage",
        "slowed", "stunned", "paralyzed", "blinded", "deafened",
        "flat-footed", "clumsy", "enfeebled", "stupefied", "hidden", "undetected", "observed",
        "grabbed", "restrained", "prone", "immobilized", "fleeing", "confused",
        "petrified", "sickened", "drained", "fatigued", "encumbered",
    })

    def _classify_object(obj: Optional[str]) -> Optional[str]:
        if not obj:
            return None
        key = _normalize_entity_key(obj)
        if key in _STAT_TERMS:
            return "affects_stat"
        if key in _CONDITION_TERMS:
            return "affects_condition"
        # Heuristic: "dying", "frightened", etc. often appear as words in phrases
        for cond in _CONDITION_TERMS:
            if cond in key or key in cond:
                return "affects_condition"
        for stat in _STAT_TERMS:
            if stat in key or key in stat:
                return "affects_stat"
        # Default to affects_stat for numeric/mechanical targets, else skip (prefer precision)
        return None

    added = 0
    seen: Set[Tuple[str, str, str]] = set()
    effect_fact_types = {
        FactType.MODIFIES, FactType.OVERRIDES, FactType.TRIGGERS, FactType.PREVENTS,
        FactType.INSTEAD_OF,
    }

    def _add_edge(source_id: str, target_id: str, relation: str, fact: "RuleFact") -> None:
        nonlocal added
        if not source_id or not target_id or source_id == target_id:
            return
        key = (source_id, target_id, relation)
        if key in seen:
            return
        chunk_id = fact_chunk_by_id.get(fact.fact_id, "")
        graph.add_edge(
            source_id,
            target_id,
            relation,
            {
                "source_document": doc_id,
                "source_chunk_id": chunk_id,
                "clause_id": fact.clause_id,
                "fact_id": fact.fact_id,
                "extraction_method": "effect_target_e3",
            },
        )
        seen.add(key)
        added += 1

    for fact in facts:
        if fact.fact_type not in effect_fact_types:
            continue
        source_id = fact_owner_by_id.get(fact.fact_id)
        if not source_id:
            continue

        for raw in (fact.object, fact.override_target):
            if not raw:
                continue
            relation = _classify_object(raw)
            if not relation:
                continue
            target_key = _normalize_entity_key(raw)
            target_id = _select_mechanic_frame_id(
                target_key, mechanic_frame_ids_by_key, entity_type_by_id
            )
            if target_id:
                _add_edge(source_id, target_id, relation, fact)

    return added


def _apply_phase1_polish(
    graph: Graph,
    facts: List["RuleFact"],
    relations: List["FactRelation"],
    fact_owner_by_id: Dict[str, str],
    entity_type_by_id: Dict[str, str],
) -> None:
    from collections import defaultdict

    from .fact_relations import RelationType
    from .rule_facts import FactType

    semantic_relation_types = {
        RelationType.APPLIES_TO_ROLE,
        RelationType.REQUIRES_LEVEL,
        RelationType.SAME_SUBJECT,
        RelationType.HAS_FAILURE_MODE,
        RelationType.CONTRASTS_WITH,
        RelationType.OVERRIDDEN_BY,
        RelationType.CHANGES_OUTCOME,
        RelationType.TRIGGERS,
        RelationType.UNLESS,
    }
    causal_fact_types = {
        FactType.TRIGGERS,
        FactType.PREVENTS,
        FactType.MODIFIES,
        FactType.OVERRIDES,
        FactType.INSTEAD_OF,
        FactType.UNLESS,
    }
    negative_override_fact_types = {
        FactType.PREVENTS,
        FactType.OVERRIDES,
        FactType.INSTEAD_OF,
        FactType.UNLESS,
    }

    facts_by_id = {fact.fact_id: fact for fact in facts}
    owned_facts_by_frame: Dict[str, List[str]] = defaultdict(list)
    for fact_id, owner_id in fact_owner_by_id.items():
        if owner_id:
            owned_facts_by_frame[owner_id].append(fact_id)

    semantic_fact_ids: Set[str] = set()
    for relation in relations:
        if relation.relation_type in semantic_relation_types:
            semantic_fact_ids.add(relation.source_fact_id)
            semantic_fact_ids.add(relation.target_fact_id)

    for node in graph.nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id or node_type not in MECHANIC_FRAME_TYPES:
            continue
        kind = node.get("mechanic_kind") or "behavioral"
        owned_ids = owned_facts_by_frame.get(node_id, [])
        has_semantic_relation = any(fact_id in semantic_fact_ids for fact_id in owned_ids)
        has_negative_override = any(
            (
                facts_by_id.get(fact_id)
                and (
                    facts_by_id[fact_id].fact_type in negative_override_fact_types
                    or facts_by_id[fact_id].override_target
                )
            )
            for fact_id in owned_ids
        )

        retrieval_target = bool(has_semantic_relation or has_negative_override)
        if kind != "behavioral":
            retrieval_target = False
        node["retrieval_target"] = retrieval_target

        if kind == "behavioral" and owned_ids:
            has_causal_fact = any(
                facts_by_id.get(fact_id)
                and facts_by_id[fact_id].fact_type in causal_fact_types
                for fact_id in owned_ids
            )
            if not has_causal_fact:
                node["mechanic_kind"] = "structural_behavioral"


def _connect_chunks_by_entity(
    graph: Graph,
    entity_to_chunks: Dict[str, Set[str]],
    max_neighbors_per_chunk: int = CHUNK_ADJACENCY_LIMIT,
) -> None:
    for entity_id, chunk_ids in entity_to_chunks.items():
        if len(chunk_ids) <= 1:
            continue
        ordered = sorted(chunk_ids)
        for idx, chunk_id in enumerate(ordered):
            neighbor_count = 0
            for neighbor_id in ordered[idx + 1 :]:
                graph.add_edge(
                    chunk_id,
                    neighbor_id,
                    STRUCTURAL_COREFERENCE_RELATION,
                    {"entity_id": entity_id, "semantic": False},
                )
                neighbor_count += 1
                if neighbor_count >= max_neighbors_per_chunk:
                    break


def _summarize_graph(graph: Graph) -> Dict[str, Any]:
    node_type_counts: Dict[str, int] = {}
    edge_relation_counts: Dict[str, int] = {}
    alias_lengths: List[int] = []
    entity_type_counts: Dict[str, int] = {}

    for node in graph.nodes:
        node_type = node.get("type", "unknown")
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
        if is_entity_like(node):
            entity_type_counts[node_type] = entity_type_counts.get(node_type, 0) + 1
            aliases = node.get("aliases") or []
            alias_lengths.append(len(aliases))

    for edge in graph.edges:
        relation = edge.get("relation", "unknown")
        edge_relation_counts[relation] = edge_relation_counts.get(relation, 0) + 1

    total_entities = sum(entity_type_counts.values())
    alias_with_multiple = sum(1 for length in alias_lengths if length > 1)
    avg_alias_length = round(sum(alias_lengths) / len(alias_lengths), 3) if alias_lengths else 0.0

    return {
        "node_counts": node_type_counts,
        "entity_type_counts": entity_type_counts,
        "edge_relation_counts": edge_relation_counts,
        "entity_count": total_entities,
        "entities_with_multiple_aliases": alias_with_multiple,
        "avg_aliases_per_entity": avg_alias_length,
        "max_aliases_per_entity": max(alias_lengths) if alias_lengths else 0,
    }


def _validate_graph(graph: Graph) -> Dict[str, List]:
    """Validate graph; return validation issues. Only entity-kind nodes require canonical_id."""
    missing_canonical = [
        node
        for node in graph.nodes
        if is_entity_like(node)
        and not _is_canonical_id(node.get("id", ""))
        and not node.get("canonical_id")
    ]
    if missing_canonical:
        sample_ids = [node.get("id") for node in missing_canonical[:5]]
        print(
            "⚠️  Graph validation: missing canonical_id for "
            f"{len(missing_canonical)} entity nodes (sample: {sample_ids})"
        )

    missing_relation = [edge for edge in graph.edges if not edge.get("relation")]
    if missing_relation:
        print(
            "⚠️  Graph validation: edges missing relation="
            f"{len(missing_relation)}"
        )
    return {"missing_canonical": missing_canonical, "missing_relation": missing_relation}


# -----------------------------------------------------------------------------
# Phase 1: Candidate extraction (pure — no graph, no canonicalization)
# -----------------------------------------------------------------------------


def _make_candidate_id(
    chunk_id: str,
    entity_type: str,
    kind: CandidateKind,
    surface_name: str,
    seq: int = 0,
) -> str:
    """Stable deterministic id for an entity candidate."""
    slug = _slugify_name(surface_name or "unnamed")[:48]
    return f"cand:{chunk_id}:{entity_type}:{slug}:{kind.value}:{seq}"


def _vocabulary_mention_to_entity_type(mention_type: str) -> Optional[str]:
    """Map mention_type (from vocabulary_loader) to graph entity_type for entity candidates."""
    mapping = {
        "mechanic": "MechanicFrame",
        "condition": "Condition",
        "role": "Ancestry",  # config overrides are often ancestry names; Class/Background same vocab
    }
    return mapping.get(mention_type.lower()) if mention_type else None


def _extract_vocabulary_entity_candidates(
    chunk: EnrichedChunk,
    chunk_id: str,
    page: Optional[int],
    vocabularies: Dict[str, Set[str]],
    candidate_seq_by_key: Dict[str, int],
) -> List[EntityCandidate]:
    """
    Extract entity candidates from vocabulary matches in chunk text.

    Used when the chunk has no entity from headers/section/tags; catches mentions
    like "You can cast Fireball as a reaction" so the chunk can describe Fireball.
    One candidate per vocabulary term that appears at word boundaries (first match per term).
    """
    from .vocabulary_loader import _is_word_boundary

    candidates: List[EntityCandidate] = []
    text = chunk.text
    text_lower = text.lower()

    for mention_type, terms in vocabularies.items():
        if not terms:
            continue
        entity_type = _vocabulary_mention_to_entity_type(mention_type)
        if not entity_type:
            continue
        kind = CandidateKind.MECHANIC_FRAME if entity_type == "MechanicFrame" else CandidateKind.ENTITY
        for term in terms:
            if len(term) < 2:
                continue
            idx = text_lower.find(term, 0)
            if idx == -1:
                continue
            if not _is_word_boundary(text_lower, idx, len(term)):
                continue
            surface = text[idx : idx + len(term)]
            entity_name = _normalize_entity_name(surface)
            if not entity_name:
                continue
            key = (chunk_id, entity_type, kind, entity_name)
            seq = candidate_seq_by_key.get(str(key), 0)
            candidate_seq_by_key[str(key)] = seq + 1
            candidates.append(
                EntityCandidate(
                    candidate_id=_make_candidate_id(chunk_id, entity_type, kind, entity_name, seq),
                    kind=kind,
                    entity_type=entity_type,
                    surface_name=entity_name,
                    chunk_id=chunk_id,
                    page=page,
                    clause_id=None,
                    extraction_method="vocabulary_match",
                    semantic=True,
                    context={"matched_surface": surface, "span": (idx, idx + len(term))},
                    confidence=0.8,
                )
            )
            break  # one candidate per term per chunk (first occurrence)
    return candidates


def extract_entity_candidates(
    chunks: List[EnrichedChunk],
    resolved_config: Optional[Any] = None,
    vocabularies: Optional[Dict[str, Set[str]]] = None,
) -> CandidateBundle:
    """
    Extract entity candidates from chunks without mutating a graph or
    resolving aliases. Returns CandidateBundle (candidates + relation_mentions).
    Phase 2 will canonicalize; Phase 3 will materialize nodes/edges.
    """
    candidates: List[EntityCandidate] = []
    relation_mentions: List[Tuple[str, str, str]] = []
    entity_type_context = _build_entity_type_context(chunks, window_size=500)
    candidate_seq_by_key: Dict[str, int] = {}

    for chunk_idx, chunk in enumerate(chunks):
        if not chunk.text.strip():
            continue
        chunk_id = chunk.id
        chunk_has_entity_candidate = False
        entity_type_map = {
            "spell": "Spell",
            "feat": "Feat",
            "item": "Item",
            "rule": "Rule",
        }
        primary_entity_surface: Optional[str] = None

        entity_type = entity_type_map.get(chunk.content_kind)
        if entity_type:
            entity_name = _extract_entity_name(chunk)
            if entity_type == "Rule" and not entity_name:
                entity_name = ""
            if entity_name:
                key = (chunk_id, entity_type, CandidateKind.ENTITY, entity_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, entity_type, CandidateKind.ENTITY, entity_name, seq
                        ),
                        kind=CandidateKind.ENTITY,
                        entity_type=entity_type,
                        surface_name=_normalize_entity_name(entity_name),
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=True,
                        context={
                            "content_kind": chunk.content_kind,
                            "block_type": chunk.block_type,
                            "section_path": chunk.section_path,
                        },
                    )
                )
                primary_entity_surface = _normalize_entity_name(entity_name)
                chunk_has_entity_candidate = True
                if chunk.content_kind in {"feat", "spell", "rule", "item"}:
                    mf_key = (chunk_id, "MechanicFrame", CandidateKind.MECHANIC_FRAME, entity_name)
                    mf_seq = candidate_seq_by_key.get(str(mf_key), 0)
                    candidate_seq_by_key[str(mf_key)] = mf_seq + 1
                    candidates.append(
                        EntityCandidate(
                            candidate_id=_make_candidate_id(
                                chunk_id, "MechanicFrame", CandidateKind.MECHANIC_FRAME, entity_name, mf_seq
                            ),
                            kind=CandidateKind.MECHANIC_FRAME,
                            entity_type="MechanicFrame",
                            surface_name=primary_entity_surface,
                            chunk_id=chunk_id,
                            page=chunk.page,
                            clause_id=None,
                            extraction_method="heuristic",
                            semantic=True,
                            context={"content_kind": chunk.content_kind},
                        )
                    )

        section_entity_type = _infer_section_entity_type(chunk)
        if section_entity_type and section_entity_type != entity_type:
            section_entity_name = _extract_section_entity_name(chunk)
            if section_entity_name and _is_simple_entity_name(section_entity_name):
                key = (chunk_id, section_entity_type, CandidateKind.ENTITY, section_entity_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, section_entity_type, CandidateKind.ENTITY, section_entity_name, seq
                        ),
                        kind=CandidateKind.ENTITY,
                        entity_type=section_entity_type,
                        surface_name=_normalize_entity_name(section_entity_name),
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="section_header",
                        semantic=False,
                        context={"section_path": chunk.section_path},
                    )
                )
                chunk_has_entity_candidate = True

        tag_entity_type = _infer_tag_entity_type(chunk)
        if (
            tag_entity_type
            and tag_entity_type != entity_type
            and tag_entity_type != section_entity_type
        ):
            tag_entity_name = _extract_tag_entity_name(chunk)
            if tag_entity_name and _is_simple_entity_name(tag_entity_name):
                key = (chunk_id, tag_entity_type, CandidateKind.ENTITY, tag_entity_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, tag_entity_type, CandidateKind.ENTITY, tag_entity_name, seq
                        ),
                        kind=CandidateKind.ENTITY,
                        entity_type=tag_entity_type,
                        surface_name=_normalize_entity_name(tag_entity_name),
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="tag",
                        semantic=False,
                        context={"tags": chunk.tags},
                    )
                )
                chunk_has_entity_candidate = True

        if chunk.section_path and chunk.tags:
            for tag in chunk.tags:
                tag_lower = tag.lower()
                path_entity_name = None
                path_type = None
                if "ancestr" in tag_lower or "heritage" in tag_lower:
                    path_entity_name = _extract_named_entity_from_path(chunk, "Ancestry")
                    path_type = "Ancestry"
                elif "class" in tag_lower and "subclass" not in tag_lower:
                    path_entity_name = _extract_named_entity_from_path(chunk, "Class")
                    path_type = "Class"
                elif "background" in tag_lower:
                    path_entity_name = _extract_named_entity_from_path(chunk, "Background")
                    path_type = "Background"
                if path_entity_name and path_type:
                    key = (chunk_id, path_type, CandidateKind.ENTITY, path_entity_name)
                    seq = candidate_seq_by_key.get(str(key), 0)
                    candidate_seq_by_key[str(key)] = seq + 1
                    candidates.append(
                        EntityCandidate(
                            candidate_id=_make_candidate_id(
                                chunk_id, path_type, CandidateKind.ENTITY, path_entity_name, seq
                            ),
                            kind=CandidateKind.ENTITY,
                            entity_type=path_type,
                            surface_name=_normalize_entity_name(path_entity_name),
                            chunk_id=chunk_id,
                            page=chunk.page,
                            clause_id=None,
                            extraction_method="section_path",
                            semantic=False,
                            context={"tags": chunk.tags, "section_path": chunk.section_path},
                        )
                    )
                    chunk_has_entity_candidate = True
                    break

        if chunk.block_type in {"SectionHeader", "Title"}:
            header_text = _strip_markdown_title(chunk.text)
            if _is_simple_entity_name(header_text) and (
                chunk.is_rule_bearing or _has_rule_bearing_followup(chunks, chunk_idx)
            ):
                key = (chunk_id, "MechanicFrame", CandidateKind.MECHANIC_FRAME, header_text)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "MechanicFrame", CandidateKind.MECHANIC_FRAME, header_text, seq
                        ),
                        kind=CandidateKind.MECHANIC_FRAME,
                        entity_type="MechanicFrame",
                        surface_name=_normalize_entity_name(header_text),
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="header_promotion",
                        semantic=False,
                        context={"block_type": chunk.block_type},
                    )
                )
                chunk_has_entity_candidate = True

        if chunk.block_type == "SectionHeader" and chunk_idx in entity_type_context:
            header_text = _strip_markdown_title(chunk.text)
            if _is_simple_entity_name(header_text):
                context_entity_type = entity_type_context[chunk_idx]
                entity_name = _normalize_entity_name(header_text)
                if (
                    entity_name
                    and entity_name.lower() not in _PATH_CATEGORY_KEYWORDS
                    and _has_entity_signature(chunks, chunk_idx, context_entity_type)
                ):
                    key = (chunk_id, context_entity_type, CandidateKind.ENTITY, entity_name)
                    seq = candidate_seq_by_key.get(str(key), 0)
                    candidate_seq_by_key[str(key)] = seq + 1
                    candidates.append(
                        EntityCandidate(
                            candidate_id=_make_candidate_id(
                                chunk_id, context_entity_type, CandidateKind.ENTITY, entity_name, seq
                            ),
                            kind=CandidateKind.ENTITY,
                            entity_type=context_entity_type,
                            surface_name=entity_name,
                            chunk_id=chunk_id,
                            page=chunk.page,
                            clause_id=None,
                            extraction_method="context_header",
                            semantic=False,
                            context={"entity_type_context": context_entity_type},
                        )
                    )
                chunk_has_entity_candidate = True

        if not chunk_has_entity_candidate:
            header_scope = _extract_header_scope_entity(chunk)
            if header_scope:
                entity_name_hs, entity_type_hs = header_scope
                key = (chunk_id, entity_type_hs, CandidateKind.ENTITY, entity_name_hs)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                kind_entity = CandidateKind.ENTITY
                if entity_type_hs == "MechanicFrame":
                    kind_entity = CandidateKind.MECHANIC_FRAME
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, entity_type_hs, kind_entity, entity_name_hs, seq
                        ),
                        kind=kind_entity,
                        entity_type=entity_type_hs,
                        surface_name=entity_name_hs,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="header_scope",
                        semantic=True,
                        context={"section_path": chunk.section_path},
                    )
                )
                if entity_type_hs in {"Spell", "Feat", "Rule", "Item"}:
                    mf_key = (
                        chunk_id,
                        "MechanicFrame",
                        CandidateKind.MECHANIC_FRAME,
                        entity_name_hs,
                    )
                    mf_seq = candidate_seq_by_key.get(str(mf_key), 0)
                    candidate_seq_by_key[str(mf_key)] = mf_seq + 1
                    candidates.append(
                        EntityCandidate(
                            candidate_id=_make_candidate_id(
                                chunk_id,
                                "MechanicFrame",
                                CandidateKind.MECHANIC_FRAME,
                                entity_name_hs,
                                mf_seq,
                            ),
                            kind=CandidateKind.MECHANIC_FRAME,
                            entity_type="MechanicFrame",
                            surface_name=entity_name_hs,
                            chunk_id=chunk_id,
                            page=chunk.page,
                            clause_id=None,
                            extraction_method="header_scope",
                            semantic=True,
                            context={"section_path": chunk.section_path},
                        )
                    )

        if not chunk_has_entity_candidate and vocabularies:
            vocab_candidates = _extract_vocabulary_entity_candidates(
                chunk, chunk_id, chunk.page, vocabularies, candidate_seq_by_key
            )
            for c in vocab_candidates:
                candidates.append(c)
            if vocab_candidates:
                chunk_has_entity_candidate = True

        if primary_entity_surface:
            for trait in chunk.traits:
                trait_name = _normalize_entity_name(trait)
                if not trait_name:
                    continue
                key = (chunk_id, "Trait", CandidateKind.TRAIT, trait_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "Trait", CandidateKind.TRAIT, trait_name, seq
                        ),
                        kind=CandidateKind.TRAIT,
                        entity_type="Trait",
                        surface_name=trait_name,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=False,
                        context={"primary_entity_surface_name": primary_entity_surface},
                    )
                )
            for tradition in chunk.traditions:
                tradition_name = _normalize_entity_name(tradition)
                if not tradition_name:
                    continue
                key = (chunk_id, "Tradition", CandidateKind.TRADITION, tradition_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "Tradition", CandidateKind.TRADITION, tradition_name, seq
                        ),
                        kind=CandidateKind.TRADITION,
                        entity_type="Tradition",
                        surface_name=tradition_name,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=False,
                        context={"primary_entity_surface_name": primary_entity_surface},
                    )
                )
            if chunk.spell_rank is not None:
                rank_name = f"Rank {chunk.spell_rank}"
                key = (chunk_id, "SpellRank", CandidateKind.SPELL_RANK, rank_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "SpellRank", CandidateKind.SPELL_RANK, rank_name, seq
                        ),
                        kind=CandidateKind.SPELL_RANK,
                        entity_type="SpellRank",
                        surface_name=rank_name,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=False,
                        context={"primary_entity_surface_name": primary_entity_surface},
                    )
                )
            for tag in chunk.tags:
                tag_name = _normalize_entity_name(tag)
                if not tag_name:
                    continue
                key = (chunk_id, "Tag", CandidateKind.TAG, tag_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "Tag", CandidateKind.TAG, tag_name, seq
                        ),
                        kind=CandidateKind.TAG,
                        entity_type="Tag",
                        surface_name=tag_name,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=False,
                        context={"primary_entity_surface_name": primary_entity_surface},
                    )
                )
            for stat_key, stat_value in (chunk.spell_stats or {}).items():
                stat_name = _normalize_entity_name(f"{stat_key}: {stat_value}")
                if not stat_name:
                    continue
                key = (chunk_id, "SpellStat", CandidateKind.SPELL_STAT, stat_name)
                seq = candidate_seq_by_key.get(str(key), 0)
                candidate_seq_by_key[str(key)] = seq + 1
                candidates.append(
                    EntityCandidate(
                        candidate_id=_make_candidate_id(
                            chunk_id, "SpellStat", CandidateKind.SPELL_STAT, stat_name, seq
                        ),
                        kind=CandidateKind.SPELL_STAT,
                        entity_type="SpellStat",
                        surface_name=stat_name,
                        chunk_id=chunk_id,
                        page=chunk.page,
                        clause_id=None,
                        extraction_method="heuristic",
                        semantic=False,
                        context={
                            "primary_entity_surface_name": primary_entity_surface,
                            "stat_key": stat_key,
                            "stat_value": stat_value,
                        },
                    )
                )

        for relation, target_name in _extract_relation_mentions(chunk.text):
            relation_mentions.append((chunk_id, relation, target_name))

    return CandidateBundle(candidates=candidates, relation_mentions=relation_mentions)


# -----------------------------------------------------------------------------
# Phase 2: Canonicalization + alias resolution (pure transform)
# -----------------------------------------------------------------------------


def canonicalize_candidates(
    bundle: CandidateBundle,
    chunks: List[EnrichedChunk],
    ruleset_id: str,
    doc_id: str,
    resolved_config: Optional[Any] = None,
) -> CanonicalizationResult:
    """
    Resolve aliases and map each candidate to a canonical entity.
    Deterministic, order-preserving (first occurrence wins per entity_type + canonical_key).
    No graph mutation; returns CanonicalizationResult for Phase 3 to consume.
    """
    alias_map = _build_entity_alias_map(chunks, resolved_config)
    canonical_entities: Dict[str, CanonicalEntity] = {}
    candidate_to_canonical: Dict[str, str] = {}
    namekey_to_canonical: Dict[str, str] = {}
    seen_canonical_keys: Dict[Tuple[str, str], str] = {}  # (entity_type, canonical_key) -> canonical_id

    for c in bundle.candidates:
        resolved_name, alias_source = _resolve_alias_name(c.surface_name, alias_map)
        if not resolved_name or not _is_reasonable_canonical(resolved_name):
            continue
        canonical_key = _normalize_entity_key(resolved_name)
        canonical_id = _canonical_entity_id(
            ruleset_id, c.entity_type, resolved_name, c.candidate_id
        )
        group_key = (c.entity_type, canonical_key)
        if group_key not in seen_canonical_keys:
            seen_canonical_keys[group_key] = canonical_id
            aliases_list: List[str] = [resolved_name]
            if alias_source and alias_source not in aliases_list:
                aliases_list.append(alias_source)
            surface_norm = _normalize_entity_name(c.surface_name)
            if surface_norm and surface_norm not in aliases_list:
                aliases_list.append(surface_norm)
            entity_role = (
                "mechanic_frame"
                if c.entity_type in MECHANIC_FRAME_TYPES
                else "entity"
            )
            entity_role = c.context.get("entity_role", entity_role)
            provenance: Dict[str, Any] = {
                "chunk_id": c.chunk_id,
                "page": c.page,
                "extraction_method": c.extraction_method,
            }
            canonical_entities[canonical_id] = CanonicalEntity(
                canonical_id=canonical_id,
                entity_type=c.entity_type,
                name=resolved_name,
                canonical_key=canonical_key,
                aliases=aliases_list,
                entity_role=entity_role,
                provenance=provenance,
            )
            for a in aliases_list:
                key = _normalize_entity_key(a)
                if key:
                    namekey_to_canonical[key] = canonical_id
        else:
            canonical_id = seen_canonical_keys[group_key]
            resolved_key = _normalize_entity_key(resolved_name)
            if resolved_key:
                namekey_to_canonical.setdefault(resolved_key, canonical_id)
            if alias_source:
                namekey_to_canonical.setdefault(
                    _normalize_entity_key(alias_source), canonical_id
                )
        candidate_to_canonical[c.candidate_id] = canonical_id

    return CanonicalizationResult(
        alias_map=alias_map,
        canonical_entities=canonical_entities,
        candidate_to_canonical=candidate_to_canonical,
        namekey_to_canonical=namekey_to_canonical,
    )


# -----------------------------------------------------------------------------
# Phase 0: Structural graph seed (pure, dumb — no entities, no heuristics)
# -----------------------------------------------------------------------------


def _build_structural_seed(
    doc_id: str,
    chunks: List[EnrichedChunk],
    ruleset_id: str,
    book_id: str,
) -> StructuralSeed:
    """
    Build only document/section/chunk nodes and contains/next edges.
    Deterministic, order-preserving, no entity or alias logic.
    """
    doc_node: Dict[str, Any] = {
        "id": doc_id,
        "type": "document",
        "name": doc_id,
        "ruleset_id": ruleset_id,
        "book_id": book_id,
    }
    section_node_list: List[Dict[str, Any]] = []
    section_index: Dict[str, str] = {}
    chunk_node_list: List[Dict[str, Any]] = []
    edge_list: List[Dict[str, Any]] = []
    chunk_order: List[str] = []

    prev_chunk_id: Optional[str] = None

    for chunk in chunks:
        if not chunk.text.strip():
            continue

        chunk_id = chunk.id
        chunk_node_list.append({
            "id": chunk_id,
            "type": "chunk",
            "content_kind": chunk.content_kind,
            "page": chunk.page,
            "is_rule_bearing": chunk.is_rule_bearing,
            "tags": chunk.tags,
            "spell_rank": chunk.spell_rank,
            "source_document": doc_id,
            "ruleset_id": ruleset_id,
            "book_id": book_id,
            "chapter_id": _derive_chapter_id(book_id, chunk.section_path),
            "section_path": chunk.section_path,
            "extraction_method": "marker_enrichment",
        })
        edge_list.append({
            "source": doc_id,
            "target": chunk_id,
            "relation": "contains",
            "source_document": doc_id,
            "page": chunk.page,
            "source_chunk_id": chunk_id,
            "extraction_method": "marker_enrichment",
        })
        chunk_order.append(chunk_id)

        if chunk.section_path:
            section_key = " > ".join(chunk.section_path)
            if section_key not in section_index:
                section_node_id = f"{doc_id}::section::{section_key}"
                section_index[section_key] = section_node_id
                section_node_list.append({
                    "id": section_node_id,
                    "type": "section",
                    "section_path": chunk.section_path,
                    "name": chunk.section_path[-1] if chunk.section_path else "",
                    "source_document": doc_id,
                    "ruleset_id": ruleset_id,
                    "book_id": book_id,
                    "chapter_id": _derive_chapter_id(book_id, chunk.section_path),
                })
                edge_list.append({
                    "source": doc_id,
                    "target": section_node_id,
                    "relation": "contains",
                    "source_document": doc_id,
                    "page": chunk.page,
                    "source_chunk_id": chunk_id,
                    "extraction_method": "marker_enrichment",
                })
            edge_list.append({
                "source": section_index[section_key],
                "target": chunk_id,
                "relation": "contains",
                "source_document": doc_id,
                "page": chunk.page,
                "source_chunk_id": chunk_id,
                "extraction_method": "marker_enrichment",
            })

        if prev_chunk_id:
            edge_list.append({
                "source": prev_chunk_id,
                "target": chunk_id,
                "relation": "next",
                "source_document": doc_id,
                "page": chunk.page,
                "source_chunk_id": chunk_id,
                "extraction_method": "marker_enrichment",
            })
        prev_chunk_id = chunk_id

    return StructuralSeed(
        doc_node=doc_node,
        section_nodes=section_node_list,
        chunk_nodes=chunk_node_list,
        edges=edge_list,
        section_index=section_index,
        chunk_order=chunk_order,
    )


def _apply_structural_seed(graph: Graph, seed: StructuralSeed) -> None:
    """Apply Phase 0 seed to graph: append nodes and edges in stable order. Updates node_index."""
    graph.nodes.append(seed.doc_node)
    graph.node_index[seed.doc_node["id"]] = len(graph.nodes) - 1
    for node in seed.section_nodes:
        graph.nodes.append(node)
        graph.node_index[node["id"]] = len(graph.nodes) - 1
    for node in seed.chunk_nodes:
        graph.nodes.append(node)
        graph.node_index[node["id"]] = len(graph.nodes) - 1
    for edge in seed.edges:
        graph.edges.append(edge)


# Scope assignment constants (HANDOFF-Scope-Assignment-Improvement-Experiment)
# Context decay: scope inheritance is bounded in distance. This prevents semantic flood.
MAX_SCOPE_SPAN = 10  # Max chunks since last MF header before scope decays (baseline, always on)

# Composable scope options (orthogonal gates for experimentation)
# stop_on_primary_mf: when True, don't inherit if chunk has its own primary MF (V2)
# inherit_only_rule_bearing: when True, only rule-bearing chunks get scope (V4)
# primary_only_scope: when True, header MF cannot establish scope (V3 - invalidated, experimental only)


def apply_header_scope_describes(
    *,
    graph: Graph,
    chunks: List[EnrichedChunk],
    chunk_order: List[str],
    candidates_by_chunk: Dict[str, List[EntityCandidate]],
    canon_result: CanonicalizationResult,
    primary_canonical_id_by_chunk: Dict[str, str],
    doc_id: str,
    scope_diagnostics: Optional[Dict[str, Any]] = None,
    scope_variant: Optional[str] = None,
    max_scope_span: int = MAX_SCOPE_SPAN,
    stop_on_primary_mf: Optional[bool] = None,
    inherit_only_rule_bearing: Optional[bool] = None,
    primary_only_scope: Optional[bool] = None,
) -> None:
    """
    Phase 3b: infer scope-based describes edges (header_scope).
    Add describes(chunk_id, active_mechanic_frame_id) when a chunk inherits scope
    from the previous chunk's mechanic frame. Same edge creation semantics and
    ordering as the previous inline logic; call after all entity nodes exist.

    Scope inheritance is bounded by max_scope_span (default 10 chunks) — context decay.

    scope_variant: Optional legacy mode — "v2", "v3", "v4" map to composable options.
    Composable options (override scope_variant when provided):
      stop_on_primary_mf: don't inherit when chunk has its own primary MF
      inherit_only_rule_bearing: only rule-bearing chunks get scope
      primary_only_scope: header MF cannot establish scope (V3, invalidated)
    """
    # Resolve composable options from scope_variant if not explicitly set
    _stop_on_primary_mf = stop_on_primary_mf if stop_on_primary_mf is not None else (scope_variant == "v2")
    _inherit_only_rule_bearing = inherit_only_rule_bearing if inherit_only_rule_bearing is not None else (scope_variant == "v4")
    _primary_only_scope = primary_only_scope if primary_only_scope is not None else (scope_variant == "v3")
    chunk_by_id = {c.id: c for c in chunks}
    active_mechanic_frame_id: Optional[str] = None
    last_mf_header_chunk_idx: Optional[int] = None

    if scope_diagnostics is not None:
        scope_diagnostics["inheritance_depths"] = []

    for chunk_id in chunk_order:
        chunk = chunk_by_id.get(chunk_id)
        if not chunk or not chunk.text.strip():
            continue
        chunk_idx = next((i for i, c in enumerate(chunks) if c.id == chunk_id), -1)

        chunk_candidates = candidates_by_chunk.get(chunk_id, [])
        this_chunk_header_mf: Optional[str] = None
        for c in chunk_candidates:
            if c.kind == CandidateKind.MECHANIC_FRAME and c.extraction_method == "header_promotion":
                this_chunk_header_mf = canon_result.candidate_to_canonical.get(c.candidate_id)
                break

        this_chunk_primary_mf: Optional[str] = primary_canonical_id_by_chunk.get(chunk_id)

        # Inheritance gate: when do we add header_scope describes?
        should_inherit = _should_inherit_mechanic_frame(chunk) if not _inherit_only_rule_bearing else chunk.is_rule_bearing
        # stop_on_primary_mf: don't inherit when chunk has its own primary MF
        if _stop_on_primary_mf and this_chunk_primary_mf:
            should_inherit = False
        # max_scope_span: context decay — limit chunks since header (always applied)
        if last_mf_header_chunk_idx is not None and chunk_idx - last_mf_header_chunk_idx > max_scope_span:
            should_inherit = False
        # Existing: don't inherit when chunk's header MF equals active (chunk defines new scope)
        if active_mechanic_frame_id and active_mechanic_frame_id == this_chunk_header_mf:
            should_inherit = False

        if active_mechanic_frame_id and should_inherit:
            graph.add_edge(
                chunk_id,
                active_mechanic_frame_id,
                "describes",
                {
                    "source_document": doc_id,
                    "page": chunk.page,
                    "source_chunk_id": chunk_id,
                    "extraction_method": "header_scope",
                    "semantic": False,
                },
            )
            if scope_diagnostics is not None and last_mf_header_chunk_idx is not None:
                chunks_since_header = chunk_idx - last_mf_header_chunk_idx
                section_depth = len(chunk.section_path) if chunk.section_path else 0
                scope_diagnostics["inheritance_depths"].append({
                    "chunk_id": chunk_id,
                    "entity_id": active_mechanic_frame_id,
                    "chunks_since_header": chunks_since_header,
                    "section_depth": section_depth,
                })

        if chunk.block_type in {"SectionHeader", "Title"}:
            header_text = _strip_markdown_title(chunk.text)
            if _is_simple_entity_name(header_text) and not (
                chunk.is_rule_bearing or _has_rule_bearing_followup(chunks, chunk_idx)
            ):
                active_mechanic_frame_id = None
                last_mf_header_chunk_idx = None
            else:
                # primary_only_scope: header MF cannot establish scope (experimental, invalidated)
                if _primary_only_scope:
                    active_mechanic_frame_id = this_chunk_primary_mf or active_mechanic_frame_id
                else:
                    active_mechanic_frame_id = (
                        this_chunk_header_mf or this_chunk_primary_mf or active_mechanic_frame_id
                    )
                last_mf_header_chunk_idx = chunk_idx
        else:
            active_mechanic_frame_id = this_chunk_primary_mf or active_mechanic_frame_id


def build_chunk_graph(
    doc_id: str,
    chunks: List[EnrichedChunk],
    ruleset_id: Optional[str] = None,
    resolved_config: Optional[Any] = None,
    scope_variant: Optional[str] = None,
) -> Graph:
    """Build a doc → section → chunk graph with semantic entity nodes."""
    graph = Graph()
    inferred = None if ruleset_id else infer_ruleset_from_document_id(doc_id)
    resolved_ruleset_id = ruleset_id or inferred or doc_id
    if not ruleset_id:
        if inferred:
            print(
                f"ℹ️  Graph build: ruleset_id inferred from doc_id → {resolved_ruleset_id} "
                f"(canon:{_slugify_name(resolved_ruleset_id)}:...)."
            )
        else:
            print(
                "⚠️  Graph build: ruleset_id missing and no doc_id mapping; defaulting to doc_id "
                f"({doc_id}). Canonical IDs will be book-scoped."
            )
    print(f"Resolved ruleset_id: {resolved_ruleset_id}")
    book_id = _normalize_book_id(doc_id)

    # Phase 0: structural seed (doc/section/chunk + contains/next only)
    seed = _build_structural_seed(doc_id, chunks, resolved_ruleset_id, book_id)
    _apply_structural_seed(graph, seed)

    # Bootstrap vocabulary for Tier 2 entity extraction (vocabulary_match)
    vocabularies: Dict[str, Set[str]] = {}
    if resolved_config:
        try:
            from .vocabulary_loader import load_vocabulary_from_config

            vocabularies = load_vocabulary_from_config(resolved_config) or {}
        except Exception:  # noqa: BLE001
            pass
    vocab_for_extraction = vocabularies if any(vocabularies.values()) else None

    # Phase 1+2: candidate extraction and canonicalization (replaces inline extraction + alias_map)
    bundle = extract_entity_candidates(chunks, resolved_config, vocabularies=vocab_for_extraction)
    canon_result = canonicalize_candidates(
        bundle, chunks, resolved_ruleset_id, doc_id, resolved_config
    )
    chunk_by_id = {c.id: c for c in chunks}
    candidates_by_chunk: Dict[str, List[EntityCandidate]] = {}
    for c in bundle.candidates:
        candidates_by_chunk.setdefault(c.chunk_id, []).append(c)

    entity_registry = EntityRegistry(doc_id, resolved_ruleset_id)
    entity_to_chunks: Dict[str, Set[str]] = {}
    seen_entity_ids: Set[str] = set()
    primary_canonical_id_by_chunk: Dict[str, str] = {}
    chunk_order: List[str] = []
    alias_map = canon_result.alias_map

    for chunk_idx, chunk in enumerate(chunks):
        if not chunk.text.strip():
            continue

        chunk_id = chunk.id
        chunk_order.append(chunk_id)

        chunk_candidates = candidates_by_chunk.get(chunk_id, [])

        # Phase 3: materialize entity nodes from Phase 1+2 candidates (same order as before)
        primary_canonical_id: Optional[str] = None
        for candidate in chunk_candidates:
            canon_id = canon_result.candidate_to_canonical.get(candidate.candidate_id)
            if canon_id is None:
                continue
            cent = canon_result.canonical_entities.get(canon_id)
            if cent is None:
                continue
            ch = chunk_by_id.get(candidate.chunk_id, chunk)
            mechanic_meta = (
                _classify_mechanic_kind(
                    cent.name,
                    entity_type=cent.entity_type,
                    content_kind=ch.content_kind,
                    block_type=ch.block_type,
                    tags=ch.tags,
                )
                if cent.entity_type in MECHANIC_FRAME_TYPES
                else {}
            )
            _, delta, is_new = entity_registry.ensure_entity_node(
                entity_type=cent.entity_type,
                resolved_name=cent.name,
                alias_source=None,
                chunk_id=candidate.chunk_id,
                page=candidate.page,
                extraction_method=candidate.extraction_method,
                mechanic_meta=mechanic_meta,
                chunk_spell_rank=ch.spell_rank,
                chunk_spell_stats=ch.spell_stats,
                chunk_traits=ch.traits,
                chunk_traditions=ch.traditions,
                chunk_tags=ch.tags,
            )
            apply_delta(graph, delta)

            graph.add_edge(
                chunk_id,
                canon_id,
                "describes",
                {
                    "source_document": doc_id,
                    "page": ch.page,
                    "source_chunk_id": chunk_id,
                    "extraction_method": candidate.extraction_method,
                },
            )
            graph.add_edge(
                canon_id,
                chunk_id,
                "mentioned_in",
                {
                    "source_document": doc_id,
                    "page": ch.page,
                    "source_chunk_id": chunk_id,
                    "extraction_method": candidate.extraction_method,
                },
            )
            if cent.entity_type in CORE_ENTITY_TYPES:
                entity_to_chunks.setdefault(canon_id, set()).add(chunk_id)
            seen_entity_ids.add(canon_id)

            # First primary entity (Spell/Feat/Item/Rule or content MF) for this chunk
            if primary_canonical_id is None and (
                (candidate.entity_type in ("Spell", "Feat", "Item", "Rule"))
                or (
                    candidate.kind == CandidateKind.MECHANIC_FRAME
                    and candidate.context.get("content_kind") in ("spell", "feat", "rule", "item")
                )
            ):
                primary_canonical_id = canon_id
                primary_canonical_id_by_chunk[chunk_id] = canon_id

            # has_* edge from primary to trait/tradition/rank/tag/stat
            rel_name = HAS_RELATION_BY_KIND.get(candidate.kind)
            if rel_name and candidate.context.get("primary_entity_surface_name") and primary_canonical_id:
                graph.add_edge(
                    primary_canonical_id,
                    canon_id,
                    rel_name,
                    {
                        "source_document": doc_id,
                        "page": ch.page,
                        "source_chunk_id": chunk_id,
                        "extraction_method": "heuristic",
                    },
                )

        canonical_id = primary_canonical_id

        # Relation mentions: single source from Phase 1 (bundle.relation_mentions), no re-extraction
        chunk_relation_mentions = [
            (rel, tname) for (cid, rel, tname) in bundle.relation_mentions if cid == chunk_id
        ]
        if chunk_relation_mentions:
            for relation, target_name in chunk_relation_mentions:
                resolved_target, alias_source = _resolve_alias_name(target_name, alias_map)
                if not resolved_target:
                    continue
                target_id = entity_registry.namekey_to_id.get(_normalize_entity_key(resolved_target))
                target_was_existing = target_id is not None
                if not target_id:
                    target_id = _canonical_entity_id(
                        resolved_ruleset_id,
                        "Concept",
                        resolved_target,
                        fallback_key=f"{doc_id}:{chunk_id}:relation:{resolved_target}",
                    )
                    if target_id not in seen_entity_ids:
                        graph.add_node(
                            target_id,
                            "Concept",
                            {
                                "name": resolved_target,
                                "normalized_name": _normalize_entity_name(resolved_target),
                                "canonical_id": target_id,
                                "ruleset_id": resolved_ruleset_id,
                                "entity_role": "provisional",
                                "provisional": True,
                                "aliases": [resolved_target] + ([alias_source] if alias_source else []),
                                "source_documents": [doc_id],
                                "source_chunk_ids": [chunk_id],
                                "source_pages": [chunk.page],
                                "extraction_method": "relation_pattern",
                            },
                        )
                        seen_entity_ids.add(target_id)
                        _add_entity_index(
                            entity_registry.namekey_to_id,
                            target_id,
                            [resolved_target, alias_source] if alias_source else [resolved_target],
                        )
                source_id = canonical_id or chunk_id
                graph.add_edge(
                    source_id,
                    target_id,
                    relation,
                    {
                        "source_document": doc_id,
                        "page": chunk.page,
                        "source_chunk_id": chunk_id,
                        "extraction_method": "relation_pattern",
                    },
                )
                graph.add_edge(
                    target_id,
                    chunk_id,
                    "mentioned_in_relation",
                    {
                        "source_document": doc_id,
                        "page": chunk.page,
                        "source_chunk_id": chunk_id,
                        "extraction_method": "relation_pattern",
                    },
                )
                # Only entity_role=="entity" participates in structural_coreference (no provisionals)
                if target_was_existing and target_id:
                    idx = graph.node_index.get(target_id)
                    if idx is not None and graph.nodes[idx].get("entity_role") == "entity":
                        entity_to_chunks.setdefault(target_id, set()).add(chunk_id)

    # Phase 3b: scope-based describes (header_scope); same semantics, explicit pass
    scope_diagnostics: Dict[str, Any] = {}
    apply_header_scope_describes(
        graph=graph,
        chunks=chunks,
        chunk_order=chunk_order,
        candidates_by_chunk=candidates_by_chunk,
        canon_result=canon_result,
        primary_canonical_id_by_chunk=primary_canonical_id_by_chunk,
        doc_id=doc_id,
        scope_diagnostics=scope_diagnostics,
        scope_variant=scope_variant,
    )

    _connect_chunks_by_entity(graph, entity_to_chunks)
    summary = _summarize_graph(graph)
    summary["ruleset_id"] = resolved_ruleset_id
    summary["document_id"] = doc_id
    summary["scope_diagnostics"] = scope_diagnostics
    graph.stats = summary
    _validate_graph(graph)
    return graph


# -----------------------------------------------------------------------------
# Phase 5: Fact ownership assignment (extracted boundary)
# -----------------------------------------------------------------------------


def _assign_fact_ownership(
    graph: Graph,
    facts: List[Any],
    clause_map: Dict[str, Any],
    chunk_map: Dict[str, EnrichedChunk],
    doc_id: str,
    resolved_ruleset_id: str,
    book_id: str,
    chunk_to_entities: Dict[str, List[str]],
    describes_meta: Dict[Tuple[str, str], Dict[str, Any]],
    entity_type_by_id: Dict[str, str],
    entity_name_by_id: Dict[str, str],
    clause_mechanic_keys: Dict[str, Set[str]],
    existing_node_ids: Set[str],
    fact_node_by_id: Dict[str, Dict[str, object]],
    entity_ids_by_key_type: Dict[Tuple[str, str], List[str]],
    enrichment_variant: Optional[str] = None,
) -> OwnershipResult:
    """
    Assign each fact to a mechanic-frame owner; add belongs_to/asserts_about and
    procedure/step/parameter nodes and edges. Returns ownership result for
    downstream passes (mechanic relations, polish).
    """
    from .rule_facts import FactType

    debug_chunk_ids: Set[str] = set()
    debug_chunks_env = os.environ.get("DM_DEBUG_BELONGS_TO_CHUNKS")
    if debug_chunks_env:
        debug_chunk_ids = {
            cid.strip() for cid in debug_chunks_env.split(",") if cid.strip()
        }

    fact_owner_by_id: Dict[str, str] = {}
    fact_chunk_by_id: Dict[str, str] = {}
    multi_candidate_fact_ids: Set[str] = set()
    missing_candidate_fact_ids: Set[str] = set()
    procedure_anchor_edges: Set[Tuple[str, str, str]] = set()

    for fact in facts:
        clause = clause_map.get(fact.clause_id)
        chunk_id = clause.parent_chunk_id if clause else fact.clause_id.split("::clause_")[0]
        chunk = chunk_map.get(chunk_id)
        fact_chunk_by_id[fact.fact_id] = chunk_id
        candidate_ids = [
            eid
            for eid in chunk_to_entities.get(chunk_id, [])
            if entity_type_by_id.get(eid) in MECHANIC_FRAME_TYPES
        ]
        entity_id = None
        secondary_candidates: List[str] = []
        if candidate_ids:
            if chunk_id in debug_chunk_ids:
                debug_candidates = [
                    {
                        "id": c,
                        "name": entity_name_by_id.get(c, ""),
                        "type": entity_type_by_id.get(c, ""),
                        "extraction_method": describes_meta.get((chunk_id, c), {}).get("extraction_method"),
                    }
                    for c in candidate_ids
                ]
                print(
                    f"🔎 [BELONGS_TO DEBUG] chunk={chunk_id} "
                    f"fact={fact.fact_id} subject={fact.subject} "
                    f"candidates={debug_candidates}"
                )
            subject_key = _normalize_entity_key(fact.subject or "")
            if subject_key:
                subject_matched = [
                    c for c in candidate_ids
                    if _normalize_entity_key(entity_name_by_id.get(c, "")) == subject_key
                ]
                if subject_matched:
                    candidate_ids = subject_matched
            if (
                fact.fact_type.value == "requires"
                and fact.object
                and len(candidate_ids) > 1
            ):
                object_key = _normalize_entity_key(fact.object)
                if object_key:
                    object_matched = [
                        c for c in candidate_ids
                        if _normalize_entity_key(entity_name_by_id.get(c, "")) == object_key
                    ]
                    if object_matched:
                        candidate_ids = object_matched
            clause_keys = clause_mechanic_keys.get(fact.clause_id, set())
            if clause_keys and len(candidate_ids) > 1:
                mention_matched = [
                    c for c in candidate_ids
                    if _normalize_entity_key(entity_name_by_id.get(c, "")) in clause_keys
                ]
                if mention_matched:
                    candidate_ids = mention_matched
            if len(candidate_ids) > 1:
                header_scope_candidates = [
                    c for c in candidate_ids
                    if describes_meta.get((chunk_id, c), {}).get("extraction_method") == "header_scope"
                ]
                if header_scope_candidates:
                    candidate_ids = header_scope_candidates
            if len(candidate_ids) > 1:
                multi_candidate_fact_ids.add(fact.fact_id)
            candidate_ids = _sort_ownership_candidates(
                candidate_ids, entity_type_by_id, entity_name_by_id
            )
            entity_id = candidate_ids[0]
            if len(candidate_ids) > 1:
                secondary_candidates = [c for c in candidate_ids[1:] if c != entity_id]
        else:
            missing_candidate_fact_ids.add(fact.fact_id)

        if entity_id:
            graph.add_edge(
                fact.fact_id,
                entity_id,
                "belongs_to",
                {
                    "source_document": doc_id,
                    "source_chunk_id": chunk_id,
                    "clause_id": fact.clause_id,
                    "extraction_method": "structural_join",
                },
            )
            graph.add_edge(
                fact.fact_id,
                entity_id,
                "asserts_about",
                {
                    "source_document": doc_id,
                    "source_chunk_id": chunk_id,
                    "clause_id": fact.clause_id,
                    "extraction_method": "causal_anchor",
                },
            )
            if fact.override_target and fact.override_target.startswith("procedure:"):
                procedure_id = fact.override_target
                procedure_name = procedure_id.split(":", 1)[-1].replace("_", " ")
                if procedure_id not in existing_node_ids:
                    graph.add_node(
                        procedure_id,
                        "Procedure",
                        {
                            "name": procedure_name,
                            "canonical_id": procedure_id,
                            "ruleset_id": resolved_ruleset_id,
                            "entity_role": "procedure",
                            "source_documents": [doc_id],
                            "source_chunk_ids": [chunk_id],
                            "source_pages": [chunk.page] if chunk else [],
                            "extraction_method": "override_procedure",
                        },
                    )
                    existing_node_ids.add(procedure_id)
                step_id = _derive_procedure_step_id(
                    procedure_id, clause.text if clause else None
                )
                if step_id and step_id not in existing_node_ids:
                    step_label = step_id.split("#step:", 1)[-1].replace("_", " ")
                    graph.add_node(
                        step_id,
                        "ProcedureStep",
                        {
                            "name": f"{procedure_name} / {step_label}",
                            "canonical_id": step_id,
                            "ruleset_id": resolved_ruleset_id,
                            "entity_role": "procedure_step",
                            "procedure_id": procedure_id,
                            "source_documents": [doc_id],
                            "source_chunk_ids": [chunk_id],
                            "source_pages": [chunk.page] if chunk else [],
                            "extraction_method": "override_procedure_step",
                        },
                    )
                    existing_node_ids.add(step_id)
                    graph.add_edge(
                        step_id,
                        procedure_id,
                        "step_of",
                        {
                            "source_document": doc_id,
                            "source_chunk_id": chunk_id,
                            "clause_id": fact.clause_id,
                            "extraction_method": "procedure_step",
                        },
                    )
                threshold_override = (
                    _extract_dying_threshold_override(clause.text if clause else None)
                    if procedure_id == "procedure:dying"
                    else None
                )
                if threshold_override:
                    new_value, old_value = threshold_override
                    parameter_id = f"{procedure_id}#param:death_threshold"
                    if parameter_id not in existing_node_ids:
                        graph.add_node(
                            parameter_id,
                            "ProcedureParameter",
                            {
                                "name": "dying / death threshold",
                                "canonical_id": parameter_id,
                                "ruleset_id": resolved_ruleset_id,
                                "entity_role": "procedure_parameter",
                                "procedure_id": procedure_id,
                                "source_documents": [doc_id],
                                "source_chunk_ids": [chunk_id],
                                "source_pages": [chunk.page] if chunk else [],
                                "extraction_method": "procedure_parameter",
                            },
                        )
                        existing_node_ids.add(parameter_id)
                        graph.add_edge(
                            parameter_id,
                            procedure_id,
                            "parameter_of",
                            {
                                "source_document": doc_id,
                                "source_chunk_id": chunk_id,
                                "clause_id": fact.clause_id,
                                "extraction_method": "procedure_parameter",
                            },
                        )
                    graph.add_edge(
                        fact.fact_id,
                        parameter_id,
                        "modifies_parameter",
                        {
                            "source_document": doc_id,
                            "source_chunk_id": chunk_id,
                            "clause_id": fact.clause_id,
                            "parameter_name": "death_threshold",
                            "new_value": new_value,
                            "old_value": old_value,
                            "extraction_method": "procedure_parameter",
                        },
                    )
                graph.add_edge(
                    fact.fact_id,
                    procedure_id,
                    "targets_procedure",
                    {
                        "source_document": doc_id,
                        "source_chunk_id": chunk_id,
                        "clause_id": fact.clause_id,
                        "extraction_method": "override_procedure_target",
                    },
                )
                if step_id:
                    graph.add_edge(
                        fact.fact_id,
                        step_id,
                        "targets_step",
                        {
                            "source_document": doc_id,
                            "source_chunk_id": chunk_id,
                            "clause_id": fact.clause_id,
                            "extraction_method": "override_procedure_target",
                        },
                    )
                replace_target = step_id or procedure_id
                graph.add_edge(
                    fact.fact_id,
                    replace_target,
                    "replaces_effect",
                    {
                        "source_document": doc_id,
                        "source_chunk_id": chunk_id,
                        "clause_id": fact.clause_id,
                        "extraction_method": "override_procedure",
                    },
                )
                if enrichment_variant == "E4":
                    e4_rel = (
                        "overrides"
                        if fact.fact_type in {FactType.OVERRIDES, FactType.INSTEAD_OF, FactType.PREVENTS}
                        else "modifies"
                    )
                    graph.add_edge(
                        fact.fact_id,
                        replace_target,
                        e4_rel,
                        {
                            "source_document": doc_id,
                            "source_chunk_id": chunk_id,
                            "clause_id": fact.clause_id,
                            "extraction_method": "override_procedure",
                        },
                    )
                if fact.fact_type == FactType.PREVENTS:
                    graph.add_edge(
                        fact.fact_id,
                        replace_target,
                        "suppresses",
                        {
                            "source_document": doc_id,
                            "source_chunk_id": chunk_id,
                            "clause_id": fact.clause_id,
                            "extraction_method": "override_procedure",
                        },
                    )
                for relation, target_types, target_names in PROCEDURE_ANCHOR_MAP.get(
                    procedure_id, []
                ):
                    for target_name in target_names:
                        target_key = _normalize_entity_key(target_name)
                        if not target_key:
                            continue
                        for target_type in target_types:
                            for target_id in entity_ids_by_key_type.get(
                                (target_type, target_key), []
                            ):
                                edge_key = (procedure_id, target_id, relation)
                                if edge_key in procedure_anchor_edges:
                                    continue
                                graph.add_edge(
                                    procedure_id,
                                    target_id,
                                    relation,
                                    {
                                        "source_document": doc_id,
                                        "source_chunk_id": chunk_id,
                                        "clause_id": fact.clause_id,
                                        "extraction_method": "procedure_anchor",
                                    },
                                )
                                procedure_anchor_edges.add(edge_key)
            fact_owner_by_id[fact.fact_id] = entity_id
            if secondary_candidates:
                fact_node = fact_node_by_id.get(fact.fact_id)
                if fact_node is not None:
                    fact_node["ownership_candidates"] = list(candidate_ids)
                    fact_node["possible_context_of"] = list(secondary_candidates)

    belongs_to_count = len(fact_owner_by_id)
    print(
        "✅ Added "
        f"{belongs_to_count} BELONGS_TO edges ({belongs_to_count}/{len(facts)} facts)"
    )
    if multi_candidate_fact_ids:
        print(
            "⚠️  BELONGS_TO: "
            f"{len(multi_candidate_fact_ids)} facts had multiple mechanic-frame candidates."
        )
    if missing_candidate_fact_ids:
        print(
            "⚠️  BELONGS_TO: "
            f"{len(missing_candidate_fact_ids)} facts had no mechanic-frame candidate."
        )
    return OwnershipResult(
        fact_owner_by_id=fact_owner_by_id,
        fact_chunk_by_id=fact_chunk_by_id,
        multi_candidate_fact_ids=multi_candidate_fact_ids,
        missing_candidate_fact_ids=missing_candidate_fact_ids,
    )


def build_fact_graph(
    doc_id: str,
    chunks: List[EnrichedChunk],
    ruleset_id: Optional[str] = None,
    resolved_config: Optional[Any] = None,
    include_fact_chunk_links: bool = True,
    include_partial: bool = False,
    allow_cross_section: bool = True,
    vocabularies: Optional[Dict[str, Set[str]]] = None,
    mention_type_mappings: Optional[Dict[str, Set[str]]] = None,
    scope_variant: Optional[str] = None,
    enrichment_variant: Optional[str] = None,
    chunk_graph_payload: Optional[Dict[str, Any]] = None,
) -> Graph:
    """Build a graph with RuleFacts as nodes and typed relations as edges.

    When chunk_graph_payload is provided (e.g. loaded merged.graph.json), that graph
    is used as the chunk/entity layer and the fact layer (RuleFacts, belongs_to, etc.)
    is added on top. Otherwise the chunk graph is built from chunks via build_chunk_graph.
    """
    from .clause_units import extract_clause_units
    from .fact_relations import generate_fact_relations
    from .mentions import MentionType, extract_mentions
    from .rule_facts import extract_rule_facts
    from .vocabulary_loader import (
        _extract_mechanic_terms_from_chunk,
        load_mention_type_mappings,
        load_vocabulary_from_graph_data,
    )

    if chunk_graph_payload is not None:
        graph = graph_from_payload(chunk_graph_payload)
    else:
        graph = build_chunk_graph(
            doc_id=doc_id,
            chunks=chunks,
            ruleset_id=ruleset_id,
            resolved_config=resolved_config,
            scope_variant=scope_variant,
        )

    resolved_ruleset_id = ruleset_id or infer_ruleset_from_document_id(doc_id) or doc_id
    book_id = _normalize_book_id(doc_id)

    chunk_map = {chunk.id: chunk for chunk in chunks}
    clause_map: Dict[str, Any] = {}
    clause_mechanic_keys: Dict[str, Set[str]] = {}
    facts = []
    mechanic_mentions_by_chunk: Dict[str, Set[str]] = {}
    fact_node_by_id: Dict[str, Dict[str, object]] = {}

    if vocabularies is None:
        if mention_type_mappings is None:
            mention_type_mappings = load_mention_type_mappings(config=resolved_config)
        vocabularies = load_vocabulary_from_graph_data(graph.to_dict(), mention_type_mappings)

    mechanic_entity_types = {
        term.lower() for term in (mention_type_mappings.get("mechanic") or set())
    }

    for chunk_idx, chunk in enumerate(chunks):
        chunk_terms = _extract_mechanic_terms_from_chunk(
            {
                "text": chunk.text,
                "content_kind": chunk.content_kind,
                "block_type": chunk.block_type,
                "tags": chunk.tags,
            },
            mechanic_entity_types,
        )
        if chunk_terms and (
            chunk.is_rule_bearing or _has_rule_bearing_followup(chunks, chunk_idx)
        ):
            names = mechanic_mentions_by_chunk.setdefault(chunk.id, set())
            for term in chunk_terms:
                normalized_name = _normalize_entity_name(term)
                if normalized_name:
                    names.add(normalized_name)

        clauses = extract_clause_units(chunk)
        for clause in clauses:
            clause_map[clause.clause_id] = clause
            mentions = extract_mentions(clause, vocabularies=vocabularies)
            mechanic_mentions = [
                mention
                for mention in mentions
                if mention.mention_type == MentionType.MECHANIC
            ]
            if mechanic_mentions:
                names = mechanic_mentions_by_chunk.setdefault(chunk.id, set())
                for mention in mechanic_mentions:
                    normalized = mention.normalized or ""
                    if normalized.startswith("mechanic:"):
                        normalized = normalized.split(":", 1)[-1]
                    normalized_name = _normalize_entity_name(normalized)
                    if normalized_name:
                        names.add(normalized_name)
                        clause_mechanic_keys.setdefault(clause.clause_id, set()).add(
                            _normalize_entity_key(normalized_name)
                        )
            clause_facts = extract_rule_facts(clause, mentions, resolved_config=resolved_config)
            if not include_partial:
                clause_facts = [fact for fact in clause_facts if fact.is_complete]
            facts.extend(clause_facts)

    existing_node_ids = {node.get("id") for node in graph.nodes}
    existing_describes = {
        (edge.get("source"), edge.get("target"))
        for edge in graph.edges
        if edge.get("relation") == "describes"
    }
    mechanic_frame_by_chunk: Dict[str, str] = {}
    for chunk_id, mention_names in mechanic_mentions_by_chunk.items():
        chunk = chunk_map.get(chunk_id)
        for mention_name in sorted(mention_names):
            canonical_id = _canonical_entity_id(
                resolved_ruleset_id,
                "MechanicFrame",
                mention_name,
                fallback_key=f"{doc_id}:{chunk_id}:mechanic:{mention_name}",
            )
            if chunk_id not in mechanic_frame_by_chunk:
                mechanic_frame_by_chunk[chunk_id] = canonical_id
            if canonical_id not in existing_node_ids:
                mechanic_meta = _classify_mechanic_kind(
                    mention_name,
                    entity_type="MechanicFrame",
                    content_kind=chunk.content_kind if chunk else None,
                    block_type=chunk.block_type if chunk else None,
                    tags=chunk.tags if chunk else None,
                )
                graph.add_node(
                    canonical_id,
                    "MechanicFrame",
                    {
                        "name": mention_name,
                        "normalized_name": _normalize_entity_name(mention_name),
                        "canonical_key": _normalize_entity_key(mention_name),
                        "canonical_id": canonical_id,
                        "ruleset_id": resolved_ruleset_id,
                        "entity_role": "mechanic_frame",
                        "aliases": [mention_name],
                        "source_documents": [doc_id],
                        "source_chunk_ids": [chunk_id],
                        "source_pages": [chunk.page] if chunk else [],
                        "extraction_method": "mention_promotion",
                        **mechanic_meta,
                    },
                )
                existing_node_ids.add(canonical_id)
            if (chunk_id, canonical_id) not in existing_describes:
                graph.add_edge(
                    chunk_id,
                    canonical_id,
                    "describes",
                    {
                        "source_document": doc_id,
                        "page": chunk.page if chunk else None,
                        "source_chunk_id": chunk_id,
                        "extraction_method": "mention_promotion",
                    },
                )
                existing_describes.add((chunk_id, canonical_id))

    active_mention_frame_id: Optional[str] = None
    for chunk in chunks:
        if chunk.id in mechanic_frame_by_chunk:
            active_mention_frame_id = mechanic_frame_by_chunk[chunk.id]
        elif chunk.block_type in {"SectionHeader", "Title"}:
            header_text = _strip_markdown_title(chunk.text)
            if _is_simple_entity_name(header_text):
                active_mention_frame_id = None

        if active_mention_frame_id and _should_inherit_mechanic_frame(chunk):
            if (chunk.id, active_mention_frame_id) not in existing_describes:
                graph.add_edge(
                    chunk.id,
                    active_mention_frame_id,
                    "describes",
                    {
                        "source_document": doc_id,
                        "page": chunk.page,
                        "source_chunk_id": chunk.id,
                        "extraction_method": "mention_scope",
                        "semantic": False,
                    },
                )
                existing_describes.add((chunk.id, active_mention_frame_id))

    for fact in facts:
        clause = clause_map.get(fact.clause_id)
        chunk_id = clause.parent_chunk_id if clause else fact.clause_id.split("::clause_")[0]
        chunk = chunk_map.get(chunk_id)
        section_path = list(chunk.section_path) if chunk else []
        chapter_id = _derive_chapter_id(book_id, section_path)

        graph.add_node(
            fact.fact_id,
            "RuleFact",
            {
                **fact.to_dict(),
                "source_document": doc_id,
                "ruleset_id": resolved_ruleset_id,
                "book_id": book_id,
                "chapter_id": chapter_id,
                "source_chunk_id": chunk_id,
                "section_path": section_path,
                "extraction_method": "rule_fact_extraction",
            },
        )
        fact_node_by_id[fact.fact_id] = graph.nodes[-1]

        if include_fact_chunk_links and chunk_id:
            graph.add_edge(
                chunk_id,
                fact.fact_id,
                "has_fact",
                {
                    "source_document": doc_id,
                    "source_chunk_id": chunk_id,
                    "clause_id": fact.clause_id,
                    "extraction_method": "rule_fact_extraction",
                },
            )

    entity_type_by_id: Dict[str, str] = {}
    entity_name_by_id: Dict[str, str] = {}
    for node in graph.nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        if node_id and node_type:
            entity_type_by_id[node_id] = node_type
            if node.get("name"):
                entity_name_by_id[node_id] = node.get("name")

    entity_ids_by_key_type: Dict[Tuple[str, str], List[str]] = {}
    for node_id, name in entity_name_by_id.items():
        node_type = entity_type_by_id.get(node_id)
        if not node_type or not name:
            continue
        name_key = _normalize_entity_key(name)
        if not name_key:
            continue
        entity_ids_by_key_type.setdefault((node_type, name_key), []).append(node_id)

    chunk_to_entities: Dict[str, List[str]] = {}
    describes_meta: Dict[Tuple[str, str], Dict[str, object]] = {}
    for edge in graph.edges:
        if edge.get("relation") == "describes":
            chunk_id = edge.get("source")
            entity_id = edge.get("target")
            if chunk_id and entity_id:
                chunk_to_entities.setdefault(chunk_id, []).append(entity_id)
                key = (chunk_id, entity_id)
                existing = describes_meta.get(key)
                if existing and existing.get("extraction_method") == "header_scope":
                    continue
                describes_meta[key] = edge

    ownership_result = _assign_fact_ownership(
        graph=graph,
        facts=facts,
        clause_map=clause_map,
        chunk_map=chunk_map,
        doc_id=doc_id,
        resolved_ruleset_id=resolved_ruleset_id,
        book_id=book_id,
        chunk_to_entities=chunk_to_entities,
        describes_meta=describes_meta,
        entity_type_by_id=entity_type_by_id,
        entity_name_by_id=entity_name_by_id,
        clause_mechanic_keys=clause_mechanic_keys,
        existing_node_ids=existing_node_ids,
        fact_node_by_id=fact_node_by_id,
        entity_ids_by_key_type=entity_ids_by_key_type,
        enrichment_variant=enrichment_variant,
    )
    fact_owner_by_id = ownership_result.fact_owner_by_id
    fact_chunk_by_id = ownership_result.fact_chunk_by_id

    mechanic_relations_added = _add_mechanic_frame_relations(
        graph=graph,
        facts=facts,
        clause_mechanic_keys=clause_mechanic_keys,
        entity_name_by_id=entity_name_by_id,
        entity_type_by_id=entity_type_by_id,
        fact_owner_by_id=fact_owner_by_id,
        fact_chunk_by_id=fact_chunk_by_id,
        doc_id=doc_id,
        enrichment_variant=enrichment_variant,
    )
    if mechanic_relations_added:
        print(f"✅ Added {mechanic_relations_added} mechanic-frame relations")

    mechanic_frame_ids_by_key: Dict[str, List[str]] = {}
    if enrichment_variant in ("E2", "E3"):
        for entity_id, entity_type in entity_type_by_id.items():
            if entity_type not in MECHANIC_FRAME_TYPES:
                continue
            name = entity_name_by_id.get(entity_id, "")
            name_key = _normalize_entity_key(name)
            if name_key:
                mechanic_frame_ids_by_key.setdefault(name_key, []).append(entity_id)

    enrichment_added = _add_semantic_enrichment_edges(
        graph=graph,
        enrichment_variant=enrichment_variant,
        doc_id=doc_id,
        facts=facts if enrichment_variant in ("E2", "E3") else None,
        fact_owner_by_id=fact_owner_by_id if enrichment_variant in ("E2", "E3") else None,
        entity_name_by_id=entity_name_by_id if enrichment_variant in ("E2", "E3") else None,
        entity_type_by_id=entity_type_by_id if enrichment_variant in ("E2", "E3") else None,
        mechanic_frame_ids_by_key=mechanic_frame_ids_by_key if enrichment_variant in ("E2", "E3") else None,
        fact_chunk_by_id=fact_chunk_by_id if enrichment_variant in ("E2", "E3") else None,
    )
    if enrichment_added:
        print(f"✅ Added {enrichment_added} semantic enrichment edges (variant={enrichment_variant})")

    relations = generate_fact_relations(
        facts,
        chunk_map,
        resolved_config=resolved_config,
        allow_cross_section=allow_cross_section,
        include_partial=include_partial,
        fact_owner_by_id=fact_owner_by_id,
        owner_name_by_id=entity_name_by_id,
    )

    # Phase 5 (final): polish — mechanic_kind/retrieval_target from fact relations
    _apply_phase1_polish(
        graph=graph,
        facts=facts,
        relations=relations,
        fact_owner_by_id=fact_owner_by_id,
        entity_type_by_id=entity_type_by_id,
    )

    for relation in relations:
        graph.add_edge(
            relation.source_fact_id,
            relation.target_fact_id,
            relation.relation_type.value,
            {
                "relation_id": relation.relation_id,
                "structural_distance": relation.structural_distance,
                "same_clause": relation.same_clause,
                "same_chunk": relation.same_chunk,
                "same_section": relation.same_section,
                "inference_method": relation.inference_method,
                "confidence": relation.confidence,
            },
        )

    summary = _summarize_graph(graph)
    summary["ruleset_id"] = resolved_ruleset_id
    summary["document_id"] = doc_id
    summary["fact_count"] = len(facts)
    summary["fact_relation_count"] = len(relations)
    # Preserve scope_diagnostics from chunk graph (Phase 3b)
    if graph.stats and "scope_diagnostics" in graph.stats:
        summary["scope_diagnostics"] = graph.stats["scope_diagnostics"]
    graph.stats = summary
    _validate_graph(graph)
    return graph
