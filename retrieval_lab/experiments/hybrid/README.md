# Hybrid (dense + BM25, RRF) experiments

Same substrate and embeddings as dense; BM25 is built at eval time and fused with dense via RRF (k=60).

| Book                       | Config                        | Run (after embedding with dense config)                                                                                               |
| -------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **PHB 5e**                 | `phb_hybrid.yaml`             | `--config retrieval_lab/experiments/hybrid/phb_hybrid.yaml --run-id retrieval_lab_DnD_PHB_5.5_v2`                                     |
| **Starfinder Player Core** | `starfinder_hybrid.yaml`      | `--config retrieval_lab/experiments/hybrid/starfinder_hybrid.yaml --run-id retrieval_lab_StarFinderPlayerCore_v2`                     |
| **Swords & Wizardry**      | `swords_wizardry_hybrid.yaml` | `--config retrieval_lab/experiments/hybrid/swords_wizardry_hybrid.yaml --run-id 'retrieval_lab_Swords&Wizardry_v3_merged2000_min200'` |

Embed once with the matching config under `experiments/dense/`, then run the hybrid config with the same `--run-id`.
