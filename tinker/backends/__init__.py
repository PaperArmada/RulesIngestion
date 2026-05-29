"""LLM backend abstraction for tinker.

Selection happens at import time via the TINKER_LLM_BACKEND env var (or the
default in `base.DEFAULT_BACKEND`). Embedder is intentionally NOT routed
through this layer; it stays local on Ollama for determinism and cost.
"""

from tinker.backends.base import (
    ChatResult,
    LLMBackend,
    current_backend,
    get_backend,
    set_backend,
)

__all__ = [
    "ChatResult",
    "LLMBackend",
    "current_backend",
    "get_backend",
    "set_backend",
]
