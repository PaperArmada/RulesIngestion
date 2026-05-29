"""Backend protocol + global selector.

Roles understood by `chat()`:
  classify, classify_qrofs            -> classifier model
  extract_intent, hypothesize,
  synthesize, extract_glossary,
  label_cluster                       -> workhorse model

Backends decide their own role->model mapping internally; callers pass the
role string and stay model-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


DEFAULT_BACKEND = "ollama"


@dataclass(frozen=True)
class ChatResult:
    """One chat() return.

    `input_tokens` and `output_tokens` are best-effort. Backends fill them
    when the underlying API surfaces token counts (Gemini does;
    Ollama's prompt_eval_count + eval_count expose them too).
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMBackend(Protocol):
    name: str

    def chat(
        self,
        *,
        role: str,
        system: str,
        user: str,
        think: bool = False,
        json_format: bool = False,
        max_tokens: int | None = None,
    ) -> ChatResult: ...

    def unload_chat(self, role: str = "workhorse") -> bool:
        """Best-effort eviction of the role's model from local GPU.

        Returns True if eviction confirmed (or backend is hosted and the
        concept doesn't apply). Used by the routing layer before handing
        the GPU to the cross-encoder reranker.
        """
        ...


_BACKEND: LLMBackend | None = None


def get_backend(name: str | None = None) -> LLMBackend:
    """Return a backend by name, or the configured default.

    Resolution order: explicit `name` arg, then `TINKER_LLM_BACKEND` env
    var, then `DEFAULT_BACKEND`. Lazy-imports the implementation module
    so missing optional deps (e.g. google-genai) only error if you ask
    for that backend.
    """
    backend_name = name or os.environ.get("TINKER_LLM_BACKEND", DEFAULT_BACKEND)
    backend_name = backend_name.strip().lower()
    if backend_name in ("ollama", "local"):
        from tinker.backends.ollama_backend import OllamaBackend
        return OllamaBackend()
    if backend_name in ("gemini", "gemini-flash", "google"):
        from tinker.backends.gemini_backend import GeminiBackend
        return GeminiBackend()
    raise ValueError(
        f"Unknown TINKER_LLM_BACKEND={backend_name!r}. "
        "Valid: ollama, gemini."
    )


def current_backend() -> LLMBackend:
    """Return the process-wide backend, initializing it on first call."""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = get_backend()
    return _BACKEND


def set_backend(backend: LLMBackend | str | None) -> LLMBackend:
    """Override the process-wide backend.

    Pass a string to resolve by name, an instance to install directly, or
    None to reset (next `current_backend()` call re-reads the env var).
    Returns the now-current backend (or None-equivalent if reset).
    """
    global _BACKEND
    if backend is None:
        _BACKEND = None
        return current_backend()
    if isinstance(backend, str):
        _BACKEND = get_backend(backend)
    else:
        _BACKEND = backend
    return _BACKEND
