"""Ollama LLM backend.

Role -> model:
  classify, classify_qrofs -> qwen3:4b (classifier, fast 4B)
  everything else          -> qwen3:14b (workhorse, 14B)

`unload_chat(role)` evicts the matching model from VRAM via keep_alive=0
and polls /api/ps to confirm. The reranker step relies on this to keep
the GPU free.
"""

from __future__ import annotations

import json as _json
import time
import urllib.error
import urllib.request
from typing import Any

import ollama

from tinker.backends.base import ChatResult


MODEL_CLASSIFIER = "qwen3:4b"
MODEL_WORKHORSE = "qwen3:14b"


_CLASSIFIER_ROLES = {"classify", "classify_qrofs"}


def _model_for_role(role: str) -> str:
    if role in _CLASSIFIER_ROLES:
        return MODEL_CLASSIFIER
    return MODEL_WORKHORSE


class OllamaBackend:
    name = "ollama"

    def chat(
        self,
        *,
        role: str,
        system: str,
        user: str,
        think: bool = False,
        json_format: bool = False,
        max_tokens: int | None = None,
    ) -> ChatResult:
        model = _model_for_role(role)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "think": think,
        }
        if json_format:
            kwargs["format"] = "json"
        options: dict[str, Any] = {}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            kwargs["options"] = options

        resp = ollama.chat(**kwargs)
        raw = dict(resp)
        return ChatResult(
            text=resp["message"]["content"],
            input_tokens=int(resp.get("prompt_eval_count", 0) or 0),
            output_tokens=int(resp.get("eval_count", 0) or 0),
            raw=raw,
        )

    def unload_chat(self, role: str = "workhorse") -> bool:
        model = _model_for_role(role)
        return _unload_ollama_model(model)


def _unload_ollama_model(model: str, *, wait_seconds: float = 10.0) -> bool:
    """Best-effort eviction with poll-confirm on /api/ps."""
    try:
        ollama.generate(model=model, prompt="", keep_alive=0)
    except Exception:
        pass

    deadline = time.perf_counter() + wait_seconds
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(
                "http://localhost:11434/api/ps", timeout=2.0
            ) as resp:
                payload = _json.loads(resp.read())
            loaded = {m.get("name") for m in payload.get("models", [])}
            if model not in loaded and f"{model}:latest" not in loaded:
                return True
        except (urllib.error.URLError, OSError, ValueError):
            return False
        time.sleep(0.1)
    return False
