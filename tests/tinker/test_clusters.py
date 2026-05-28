"""Tests for tinker.introspect.clusters."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tinker.cache import TinkerCache
from tinker.introspect.clusters import (
    _build_feature_matrix,
    _choose_k_by_elbow,
    _featurize_unit,
    build_clusters,
)
from tinker.substrate import Unit


def _u(uid: str, text: str, *, path: tuple[str, ...] = (), kind: str = "prose") -> Unit:
    return Unit(
        id=uid,
        text=text,
        page=0,
        structural_path=path,
        unit_type=kind,
        document_id="t",
    )


def test_featurize_unit_returns_fixed_dim_vector() -> None:
    u = _u("u1", "**Trigger:** A creature attacks. **Effect:** Step 5 feet.", path=("Action",))
    v = _featurize_unit(u)
    assert v.dtype == np.float32
    assert v.ndim == 1
    # 5 unit_type slots + 7 numeric features = 12
    assert v.shape[0] == 12


def test_featurize_picks_up_labeled_rows() -> None:
    u_stat = _u(
        "u1",
        "**HD:** 3   **AC:** 4 [15]   **Damage:** 1d6   **Special:** Poison",
    )
    u_prose = _u("u2", "A long paragraph of regular descriptive prose with no labels.")
    v_stat = _featurize_unit(u_stat)
    v_prose = _featurize_unit(u_prose)
    # The label_hits feature (index 7) should be much higher on the stat block.
    assert v_stat[7] >= 4
    assert v_prose[7] == 0


def test_build_clusters_no_llm(tmp_path: Path) -> None:
    # 16 distinct-looking units across two clear shape families.
    units: list[Unit] = []
    for i in range(8):
        units.append(
            _u(
                f"stat-{i}",
                f"**HD:** {i + 1}  **AC:** 5  **Damage:** 1d{6 + i % 4}  **Special:** none",
            )
        )
    for i in range(8):
        units.append(
            _u(
                f"prose-{i}",
                "This is a wholly prose paragraph describing the world. "
                "It contains no labeled rows, no bold prefixes, and no numbers.",
            )
        )
    cache = TinkerCache(tmp_path / "c.sqlite")
    out = build_clusters(units, cache, k_range=(2, 4), use_llm_labels=False)
    assert out["chosen_k"] >= 2
    assert len(out["clusters"]) == out["chosen_k"]
    # The two clear shape families should be separated: at least two clusters
    # have non-trivial size, and total membership equals input size.
    non_empty = [c for c in out["clusters"] if c["size"] > 0]
    assert len(non_empty) >= 2
    assert sum(c["size"] for c in out["clusters"]) == len(units)
    for c in out["clusters"]:
        assert len(c["exemplar_unit_ids"]) <= 3
        assert len(c["exemplar_unit_ids"]) <= c["size"]


def test_choose_k_by_elbow_deterministic() -> None:
    X = np.random.RandomState(0).randn(40, 5).astype(np.float32)
    k1, _ = _choose_k_by_elbow(X, (2, 6))
    k2, _ = _choose_k_by_elbow(X, (2, 6))
    assert k1 == k2
