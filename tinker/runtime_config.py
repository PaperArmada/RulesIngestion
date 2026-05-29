"""Process-wide tunable knobs for the retrieval pipeline.

These exist so the ablation harness (and future eval scripts) can toggle
pipeline behavior in-process without threading parameters through every
call site. Defaults reproduce the local-Ollama-era configuration so that
nothing changes unless a caller deliberately mutates CFG.

Knobs:
  hypothesis_max_tokens  -- num_predict / maxOutputTokens cap on the HyDE
                            hypothesis. 200 was a local-latency accommodation
                            (qwen3:14b at ~12 tok/s); hosted models can afford
                            more.
  hypothesis_word_limit  -- the word ceiling stated in the hypothesize prompt.
                            Kept in sync with the token cap conceptually.
  think_classify         -- enable model "thinking" for the q-ROFS classifier.
  think_intent           -- enable model "thinking" for intent extraction.
  gemini_think_budget    -- Gemini thinkingBudget when thinking is ON. -1 means
                            dynamic (model decides). A large FIXED budget was
                            observed to destabilize JSON output, so -1 is the
                            default "on" value.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    hypothesis_max_tokens: int = 200
    hypothesis_word_limit: int = 120
    think_classify: bool = False
    think_intent: bool = False
    gemini_think_budget: int = -1


CFG = RuntimeConfig()
