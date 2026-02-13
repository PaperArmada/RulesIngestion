from __future__ import annotations

import pytest

from retrieval_lab.config import ExperimentConfig


def _base_config_dict() -> dict:
    return {
        "experiment_name": "x",
        "substrate_path": ".",
        "document_id": "doc",
        "query_batches": ["evals/retrieval/PHB5e/r8_gold_queries.json"],
        "models": ["all-mpnet-base-v2"],
        "retrieval_mode": "hybrid",
        "top_k": [1, 3, 5, 10],
    }


def test_config_parses_grouped_and_flat_crossref() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "crossref": {"enabled": True, "expand_top_k": 7, "expand_per_hit": 1, "expand_total_cap": 9},
        }
    )
    assert cfg.crossref_sidecar_expand is True
    assert cfg.crossref_expand_top_k == 7
    assert cfg.crossref.expand_total_cap == 9


def test_config_parses_grouped_dual_list() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "dual_list": {"enabled": True, "ku": 9, "kf": 8, "kfinal": 12, "qu": 4},
        }
    )
    assert cfg.dual_list_fusion is True
    assert cfg.dual_list_ku == 9
    assert cfg.dual_list.kfinal == 12


def test_config_validation_rejects_bm25_with_dual_list() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "retrieval_mode": "bm25",
            "models": [],
            "dual_list_fusion": True,
        }
    )
    with pytest.raises(ValueError, match="dual_list_fusion is not supported in bm25 mode"):
        cfg.validate()
