from __future__ import annotations

from retrieval_lab.dual_list_fusion import fuse_dual_list


def test_dual_list_fusion_dedupes_and_marks_both() -> None:
    u_ids = ["u1", "u2", "u3"]
    u_scores = [0.9, 0.8, 0.7]
    f_ids = ["f1", "f2"]
    f_scores = [0.6, 0.5]
    anchors = {"f1": "u2", "f2": "u4"}

    fused_ids, _, fused_meta = fuse_dual_list(
        u_ids,
        u_scores,
        f_ids,
        f_scores,
        anchors,
        Qu=2,
        Kfinal=4,
    )

    assert fused_ids[:2] == ["u1", "u2"]
    assert "u4" in fused_ids
    meta_by_id = {uid: meta for uid, meta in zip(fused_ids, fused_meta)}
    assert meta_by_id["u2"].source_list == "both"


def test_dual_list_fusion_respects_kfinal() -> None:
    fused_ids, _, _ = fuse_dual_list(
        ["u1", "u2", "u3", "u4"],
        [1.0, 0.9, 0.8, 0.7],
        ["f1", "f2", "f3"],
        [0.5, 0.4, 0.3],
        {"f1": "u5", "f2": "u6", "f3": "u7"},
        Qu=1,
        Kfinal=3,
    )
    assert len(fused_ids) == 3
