"""Test configuration for tinker.

Registers custom markers so tests that need a running Ollama daemon or a
locally-downloaded model can be gated independently of the unit-test
default.

Run unit tests only (default):
  uv run pytest tests/tinker

Include Ollama-touching integration tests:
  uv run pytest tests/tinker --tinker-ollama

Include model-download tests (slow first run, cached after):
  uv run pytest tests/tinker --tinker-model
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--tinker-ollama",
        action="store_true",
        default=False,
        help="Run tests marked requires_ollama (needs a local Ollama daemon).",
    )
    parser.addoption(
        "--tinker-model",
        action="store_true",
        default=False,
        help="Run tests marked requires_model (downloads ~GB to HF cache).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_ollama: test needs a running Ollama daemon at localhost.",
    )
    config.addinivalue_line(
        "markers",
        "requires_model: test downloads a model (~GB) on first run.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--tinker-ollama"):
        skip_ollama = pytest.mark.skip(reason="needs --tinker-ollama")
        for item in items:
            if "requires_ollama" in item.keywords:
                item.add_marker(skip_ollama)
    if not config.getoption("--tinker-model"):
        skip_model = pytest.mark.skip(reason="needs --tinker-model")
        for item in items:
            if "requires_model" in item.keywords:
                item.add_marker(skip_model)
