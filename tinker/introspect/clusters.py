"""Structural clustering of EvidenceUnits.

Pipeline:
1. Build a small hand-engineered feature vector per unit (unit_type, depth,
   length-bucket, presence of labeled-row keywords like "Trigger:" /
   "Damage:" / "AC:", bullet density, bold-marker count, digit density).
2. Standardize.
3. KMeans across k∈[6,16]; pick k by elbow (knee of the inertia curve).
4. For each cluster, pick the top-3 closest-to-centroid units as exemplars.
5. Call `tinker.llm.label_cluster` on exemplar text to get a one-sentence
   structural description.

Determinism: KMeans is initialized with random_state=42 and n_init=10;
inputs and outputs are stable for a given substrate.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
from sklearn.cluster import KMeans  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from tinker import llm as tinker_llm
from tinker.cache import TinkerCache
from tinker.substrate import Unit


_UNIT_TYPES = ("prose", "list", "heading", "callout", "table")

# Labeled-row keywords that mark structured rulebook entries.
_LABELED_ROW_KEYWORDS = (
    "trigger:",
    "effect:",
    "requirements:",
    "save:",
    "damage:",
    "ac:",
    "hp:",
    "hit dice:",
    "hd:",
    "special:",
    "class:",
    "level:",
    "challenge",
    "saving throw",
    "duration:",
    "range:",
    "components:",
    "casting time:",
    "school:",
)


def _featurize_unit(u: Unit) -> np.ndarray:
    text = u.text
    text_lower = text.lower()

    # unit_type one-hot
    type_oh = [1.0 if u.unit_type == t else 0.0 for t in _UNIT_TYPES]

    # structural depth (capped)
    depth = float(min(len(u.structural_path), 5))

    # log length
    log_len = float(np.log1p(len(text)))

    # labeled-row keyword presence (count distinct keywords matched)
    label_hits = sum(1 for kw in _LABELED_ROW_KEYWORDS if kw in text_lower)

    # bullet markers ("- ", "• ", "* ")
    bullet_count = len(re.findall(r"(?m)^\s*[-*•]\s+", text))
    bullet_rate = bullet_count / max(len(text) / 100, 1)

    # bold markers
    bold_count = text.count("**") // 2

    # digit density
    digit_chars = sum(ch.isdigit() for ch in text)
    digit_rate = digit_chars / max(len(text), 1)

    # number of "**Name:**" patterns (sub-entries)
    sub_entry_count = len(re.findall(r"\*\*[A-Z][^*\n]{1,40}[:.]?\*\*", text))

    return np.array(
        type_oh
        + [
            depth,
            log_len,
            float(label_hits),
            bullet_rate,
            float(bold_count),
            digit_rate,
            float(sub_entry_count),
        ],
        dtype=np.float32,
    )


def _build_feature_matrix(units: list[Unit]) -> np.ndarray:
    return np.stack([_featurize_unit(u) for u in units], axis=0)


def _choose_k_by_elbow(X: np.ndarray, k_range: tuple[int, int]) -> tuple[int, dict[int, float]]:
    """Knee detection: largest second derivative of inertia across k_range."""
    ks = list(range(k_range[0], k_range[1] + 1))
    inertias: dict[int, float] = {}
    for k in ks:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X)
        inertias[k] = float(km.inertia_)
    # Compute discrete second derivative; pick k with largest curvature drop.
    best_k = ks[0]
    best_curvature = -np.inf
    for i in range(1, len(ks) - 1):
        k = ks[i]
        cur = inertias[ks[i - 1]] - 2 * inertias[ks[i]] + inertias[ks[i + 1]]
        if cur > best_curvature:
            best_curvature = cur
            best_k = k
    return best_k, inertias


def _exemplars_closest_to_centroid(
    X: np.ndarray, labels: np.ndarray, centroids: np.ndarray, k: int, top_n: int = 3
) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for c in range(k):
        idxs = np.where(labels == c)[0]
        if len(idxs) == 0:
            out[c] = []
            continue
        dists = np.linalg.norm(X[idxs] - centroids[c], axis=1)
        order = np.argsort(dists)
        out[c] = [int(idxs[i]) for i in order[:top_n]]
    return out


def build_clusters(
    units: list[Unit],
    cache: TinkerCache,
    *,
    k_range: tuple[int, int] = (6, 16),
    use_llm_labels: bool = True,
    model: str = tinker_llm.MODEL_WORKHORSE,
) -> dict[str, Any]:
    """Cluster units by structural fingerprint and label each cluster.

    Returns dict with `clusters` (list of cluster dicts), `chosen_k`, and
    `inertias` (k -> inertia for transparency).
    """
    X_raw = _build_feature_matrix(units)
    scaler = StandardScaler().fit(X_raw)
    X = scaler.transform(X_raw)
    chosen_k, inertias = _choose_k_by_elbow(X, k_range)

    km = KMeans(n_clusters=chosen_k, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    exemplar_idx_per_cluster = _exemplars_closest_to_centroid(
        X, labels, km.cluster_centers_, chosen_k, top_n=3
    )

    cluster_records: list[dict[str, Any]] = []
    for c in range(chosen_k):
        member_idx = [i for i in range(len(units)) if labels[i] == c]
        exemplar_idx = exemplar_idx_per_cluster.get(c, [])
        exemplar_units = [units[i] for i in exemplar_idx]

        if use_llm_labels and exemplar_units:
            payload = {
                "role": "label_cluster",
                "exemplars": [u.text[:600] for u in exemplar_units],
            }
            cached = cache.get_llm("label_cluster", model, payload)
            if cached is not None:
                description = cached
            else:
                try:
                    description = tinker_llm.label_cluster(
                        [u.text[:600] for u in exemplar_units]
                    )
                except Exception as exc:
                    description = f"<label_cluster failed: {type(exc).__name__}>"
                cache.put_llm("label_cluster", model, payload, description)
        else:
            description = ""

        cluster_records.append(
            {
                "cluster_id": int(c),
                "description": description,
                "size": int(len(member_idx)),
                "exemplar_unit_ids": [units[i].id for i in exemplar_idx],
                "member_unit_ids": [units[i].id for i in member_idx],
            }
        )

    return {
        "chosen_k": int(chosen_k),
        "inertias": {int(k): float(v) for k, v in inertias.items()},
        "clusters": cluster_records,
    }
