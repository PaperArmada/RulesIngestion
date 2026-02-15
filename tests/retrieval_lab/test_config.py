from __future__ import annotations

import pytest

from retrieval_lab.config import ExperimentConfig


def _base_config_dict() -> dict:
    return {
        "experiment_name": "x",
        "substrate_path": ".",
        "document_id": "doc",
        "query_batches": ["evals/retrieval/PHB5e/dnd_5_e_equivalent_rag_eval_queries.json"],
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


def test_config_validate_dual_list_kfinal_lt_max_top_k_raises() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "dual_list_fusion": True,
            "dual_list_kfinal": 5,
            "top_k": [1, 3, 10],
        }
    )
    with pytest.raises(ValueError, match="dual_list_kfinal must be >= max\\(top_k\\)"):
        cfg.validate()


def test_config_validate_hybrid_rerank_requires_reranker() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "retrieval_mode": "hybrid+rerank",
            "reranker": None,
        }
    )
    with pytest.raises(ValueError, match="requires reranker"):
        cfg.validate()


def test_config_parses_two_stage_fields() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "two_stage_retrieval": True,
            "stage1_admission_k": 80,
            "stage1_query_mode": "question_plus_summary",
            "stage2_query_mode": "question_only",
            "stage2_rerank_method": "dense",
        }
    )
    assert cfg.two_stage_retrieval is True
    assert cfg.stage1_admission_k == 80
    assert cfg.stage2_rerank_method == "dense"


def test_config_validate_two_stage_cross_encoder_requires_reranker() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "two_stage_retrieval": True,
            "stage2_rerank_method": "cross_encoder",
            "reranker": None,
        }
    )
    with pytest.raises(ValueError, match="requires reranker"):
        cfg.validate()


def test_config_parses_raw_first_merge_rerank_fields() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "raw_first_merge_rerank": True,
            "raw_stage1_admission_k": 64,
            "raw_merge_rerank_top_k": 15,
            "raw_merge_score_floor": False,
            "raw_merge_rank_floor": True,
            "raw_merge_coverage_bonus": 0.1,
        }
    )
    assert cfg.raw_first_merge_rerank is True
    assert cfg.raw_stage1_admission_k == 64
    assert cfg.raw_merge_rerank_top_k == 15
    assert cfg.raw_merge_score_floor is False
    assert cfg.raw_merge_rank_floor is True
    assert cfg.raw_merge_coverage_bonus == 0.1


def test_config_validate_raw_first_merge_rerank_requires_hybrid() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "retrieval_mode": "dense",
            "raw_first_merge_rerank": True,
        }
    )
    with pytest.raises(ValueError, match="requires retrieval_mode='hybrid' or 'hybrid\\+rerank'"):
        cfg.validate()


def test_config_validate_raw_first_merge_rerank_rejects_merge_chunks() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "raw_first_merge_rerank": True,
            "merge_chunks": True,
        }
    )
    with pytest.raises(ValueError, match="requires merge_chunks=false"):
        cfg.validate()


def test_config_validate_raw_first_merge_rerank_top_k_floor() -> None:
    cfg = ExperimentConfig.from_dict(
        {
            **_base_config_dict(),
            "raw_first_merge_rerank": True,
            "raw_merge_rerank_top_k": 5,
            "top_k": [1, 3, 10],
        }
    )
    with pytest.raises(ValueError, match="raw_merge_rerank_top_k must be >= max\\(top_k\\)"):
        cfg.validate()
