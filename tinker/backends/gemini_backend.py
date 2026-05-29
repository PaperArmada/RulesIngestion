"""Gemini 2.5 Flash backend.

Reads GEMINI_API_KEY from the environment. Uses gemini-2.5-flash for every
role (no per-role model split in this first cut; revisit once we have
per-role latency/quality numbers).

Online roles run with thinking budget = 0; that's the equivalent of the
qwen3 `think=False` discipline we already enforce locally. JSON-format
requests use responseMimeType="application/json". A small retry loop
covers 429s and transient 5xx.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from tinker.backends.base import ChatResult


MODEL_DEFAULT = "gemini-2.5-flash"

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 5


def _load_env_dotenv_if_needed() -> None:
    """Load .env if the key isn't already in the process environment.

    The project keeps GEMINI_API_KEY in .env at the repo root. We don't
    want to require callers to source it manually.
    """
    if os.environ.get("GEMINI_API_KEY"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")


class GeminiBackend:
    name = "gemini"

    def __init__(
        self,
        *,
        model: str = MODEL_DEFAULT,
        api_key: str | None = None,
    ) -> None:
        _load_env_dotenv_if_needed()
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env or export it before "
                "selecting the gemini backend."
            )
        self._client = genai.Client(api_key=key)
        self._model = model

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
        config_kwargs: dict[str, Any] = {
            "systemInstruction": system,
            "temperature": 0.0,
            "seed": 42,
        }
        if max_tokens is not None:
            config_kwargs["maxOutputTokens"] = max_tokens
        if json_format:
            config_kwargs["responseMimeType"] = "application/json"
        # `think=False` -> thinkingBudget 0 (matches our Qwen3 discipline).
        # `think=True`  -> CFG.gemini_think_budget (-1 = dynamic, model
        # decides). A large FIXED budget was observed to push the model into
        # out-of-range JSON values, so dynamic is the default "on".
        from tinker.runtime_config import CFG
        budget = CFG.gemini_think_budget if think else 0
        config_kwargs["thinkingConfig"] = types.ThinkingConfig(thinkingBudget=budget)

        config = types.GenerateContentConfig(**config_kwargs)
        resp = _generate_with_retry(
            client=self._client,
            model=self._model,
            contents=user,
            config=config,
        )

        text = resp.text or ""
        usage = resp.usage_metadata
        return ChatResult(
            text=text,
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
            raw={"model": self._model, "response_id": resp.response_id},
        )

    def unload_chat(self, role: str = "workhorse") -> bool:
        # Hosted; no local VRAM to free. Return True so callers don't
        # treat it as a failure.
        return True


def _generate_with_retry(
    *,
    client: genai.Client,
    model: str,
    contents: str,
    config: types.GenerateContentConfig,
):
    """Retry on 429 / transient 5xx with jittered exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None)
            if status in _RETRY_STATUS and attempt < _MAX_RETRIES - 1:
                wait = (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(wait)
                last_exc = exc
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry loop exited without returning")
