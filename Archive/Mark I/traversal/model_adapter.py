"""
Provider-agnostic LLM interface for query expansion.

Supports:
- OpenAI (GPT-5.2, GPT-4o-mini, GPT-4o) via Responses API
- Anthropic (Claude Haiku, Claude Sonnet)
- Google (Gemini Flash)
- Local models (via OpenAI-compatible API)

Each provider implements a common interface for text generation.

Note: OpenAI models use the Responses API (recommended for all new projects).
See: Docs/architecture/OpenAI_Responses_API.md for details.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ModelProvider(Enum):
    """Supported model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"


@dataclass
class ExpansionModelConfig:
    """
    Configuration for an expansion model.
    
    Attributes:
        name: Human-readable model name
        provider: Which provider (openai, anthropic, google, local)
        model_id: Provider-specific model identifier
        temperature: Sampling temperature (0.0 = deterministic)
        max_tokens: Maximum tokens in response
        api_base: Optional custom API base URL (for local models)
        extra_params: Provider-specific parameters
    """
    name: str
    provider: ModelProvider
    model_id: str
    temperature: float = 0.3
    max_tokens: int = 500
    api_base: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


# Pre-configured model options for easy switching
EXPANSION_MODELS: Dict[str, ExpansionModelConfig] = {
    "gpt-5.2": ExpansionModelConfig(
        name="GPT-5.2",
        provider=ModelProvider.OPENAI,
        model_id="gpt-5.2",
        temperature=0.3,
        max_tokens=500,
    ),
    "gpt-5-mini": ExpansionModelConfig(
        name="GPT-5 Mini",
        provider=ModelProvider.OPENAI,
        model_id="gpt-5-mini",
        temperature=0.3,
        max_tokens=500,
    ),
    "gpt-5-nano": ExpansionModelConfig(
        name="GPT-5 Nano",
        provider=ModelProvider.OPENAI,
        model_id="gpt-5-nano",
        temperature=0.3,
        max_tokens=500,
    ),
}

# Default model for query expansion
DEFAULT_EXPANSION_MODEL = "gpt-5.2"


@dataclass
class GenerationResult:
    """Result from a text generation call."""
    text: str
    model_id: str
    provider: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    @property
    def cost_estimate_usd(self) -> float:
        """Rough cost estimate based on typical pricing."""
        # Very rough estimates per 1K tokens (blended input/output)
        cost_per_1k = {
            "gpt-5.2": 0.003,        # Estimated GPT-5 pricing
            "gpt-5": 0.003,          # Estimated GPT-5 pricing
            "gpt-4o-mini": 0.00015,  # $0.15 per 1M input
            "gpt-4o": 0.0025,        # $2.50 per 1M input
            "claude-3-5-haiku": 0.0008,
            "claude-3-5-sonnet": 0.003,
            "gemini-2.0-flash": 0.0001,
            "local": 0.0,
        }
        # Try exact match first, then prefix match
        rate = cost_per_1k.get(self.model_id)
        if rate is None:
            # Try prefix matching for versioned models
            for model_prefix, model_rate in cost_per_1k.items():
                if self.model_id.startswith(model_prefix):
                    rate = model_rate
                    break
            else:
                rate = 0.001  # Default fallback
        return (self.total_tokens / 1000) * rate


class ModelAdapter(ABC):
    """Abstract base class for model adapters."""
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        """
        Generate text from prompt.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            GenerationResult with generated text and metadata
        """
        pass
    
    @property
    @abstractmethod
    def config(self) -> ExpansionModelConfig:
        """Get the model configuration."""
        pass


class OpenAIAdapter(ModelAdapter):
    """
    Adapter for OpenAI models using the Responses API.
    
    The Responses API is OpenAI's recommended API for all new projects.
    See: Docs/architecture/OpenAI_Responses_API.md
    """
    
    def __init__(self, model_config: ExpansionModelConfig):
        self._config = model_config
        self._client = None
    
    @property
    def config(self) -> ExpansionModelConfig:
        return self._config
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                self._client = OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        """
        Generate text using the OpenAI Responses API.
        
        Uses:
        - `instructions` parameter for system-level prompts (developer role)
        - `input` parameter for user prompts
        - `output_text` convenience accessor for response text
        """
        import time
        
        client = self._get_client()
        
        # Build request parameters for Responses API
        request_params = {
            "model": self._config.model_id,
            "input": prompt,
            "temperature": self._config.temperature,
            "max_output_tokens": self._config.max_tokens,
            **self._config.extra_params,
        }
        
        # Add instructions if system prompt provided
        if system_prompt:
            request_params["instructions"] = system_prompt
        
        start = time.perf_counter()
        response = client.responses.create(**request_params)
        latency_ms = (time.perf_counter() - start) * 1000
        
        # Extract token usage from response
        # The Responses API provides usage in the response object
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        if hasattr(response, 'usage') and response.usage:
            input_tokens = getattr(response.usage, 'input_tokens', 0) or 0
            output_tokens = getattr(response.usage, 'output_tokens', 0) or 0
            total_tokens = input_tokens + output_tokens
        
        return GenerationResult(
            text=response.output_text or "",
            model_id=self._config.model_id,
            provider="openai",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic Claude models."""
    
    def __init__(self, model_config: ExpansionModelConfig):
        self._config = model_config
        self._client = None
    
    @property
    def config(self) -> ExpansionModelConfig:
        return self._config
    
    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
                self._client = Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        return self._client
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        import time
        
        client = self._get_client()
        
        start = time.perf_counter()
        response = client.messages.create(
            model=self._config.model_id,
            max_tokens=self._config.max_tokens,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
            temperature=self._config.temperature,
            **self._config.extra_params,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        
        text = ""
        if response.content:
            text = response.content[0].text if hasattr(response.content[0], 'text') else str(response.content[0])
        
        return GenerationResult(
            text=text,
            model_id=self._config.model_id,
            provider="anthropic",
            latency_ms=latency_ms,
            input_tokens=response.usage.input_tokens if response.usage else 0,
            output_tokens=response.usage.output_tokens if response.usage else 0,
            total_tokens=(response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
        )


class GoogleAdapter(ModelAdapter):
    """Adapter for Google Gemini models."""
    
    def __init__(self, model_config: ExpansionModelConfig):
        self._config = model_config
        self._client = None
    
    @property
    def config(self) -> ExpansionModelConfig:
        return self._config
    
    def _get_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY environment variable not set")
                genai.configure(api_key=api_key)
                self._client = genai.GenerativeModel(self._config.model_id)
            except ImportError:
                raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        return self._client
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        import time
        
        client = self._get_client()
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        start = time.perf_counter()
        response = client.generate_content(
            full_prompt,
            generation_config={
                "temperature": self._config.temperature,
                "max_output_tokens": self._config.max_tokens,
            },
        )
        latency_ms = (time.perf_counter() - start) * 1000
        
        # Google doesn't provide token counts in the same way
        text = response.text if hasattr(response, 'text') else ""
        
        return GenerationResult(
            text=text,
            model_id=self._config.model_id,
            provider="google",
            latency_ms=latency_ms,
            # Estimate tokens (roughly 4 chars per token)
            input_tokens=len(full_prompt) // 4,
            output_tokens=len(text) // 4,
            total_tokens=(len(full_prompt) + len(text)) // 4,
        )


class LocalAdapter(ModelAdapter):
    """Adapter for local models via OpenAI-compatible API (e.g., llama.cpp, vLLM)."""
    
    def __init__(self, model_config: ExpansionModelConfig):
        self._config = model_config
        self._client = None
    
    @property
    def config(self) -> ExpansionModelConfig:
        return self._config
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_base = self._config.api_base or "http://localhost:8080/v1"
                self._client = OpenAI(
                    api_key="not-needed",  # Local servers typically don't need API key
                    base_url=api_base,
                )
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        import time
        
        client = self._get_client()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        start = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=self._config.model_id,
                messages=messages,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            
            return GenerationResult(
                text=response.choices[0].message.content or "",
                model_id=self._config.model_id,
                provider="local",
                latency_ms=latency_ms,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            # Return error as text for debugging
            return GenerationResult(
                text=f"ERROR: {str(e)}",
                model_id=self._config.model_id,
                provider="local",
                latency_ms=latency_ms,
            )


def create_adapter(model_name_or_config: Union[str, ExpansionModelConfig]) -> ModelAdapter:
    """
    Factory function to create the appropriate model adapter.
    
    Args:
        model_name_or_config: Either a model name from EXPANSION_MODELS,
                             or a custom ExpansionModelConfig
                             
    Returns:
        Configured ModelAdapter instance
        
    Raises:
        ValueError: If model name not found and not a config object
    """
    if isinstance(model_name_or_config, str):
        if model_name_or_config not in EXPANSION_MODELS:
            raise ValueError(
                f"Unknown model: {model_name_or_config}. "
                f"Available: {list(EXPANSION_MODELS.keys())}"
            )
        config = EXPANSION_MODELS[model_name_or_config]
    else:
        config = model_name_or_config
    
    adapter_map = {
        ModelProvider.OPENAI: OpenAIAdapter,
        ModelProvider.ANTHROPIC: AnthropicAdapter,
        ModelProvider.GOOGLE: GoogleAdapter,
        ModelProvider.LOCAL: LocalAdapter,
    }
    
    adapter_class = adapter_map.get(config.provider)
    if adapter_class is None:
        raise ValueError(f"Unsupported provider: {config.provider}")
    
    return adapter_class(config)


def list_available_models() -> List[str]:
    """List all pre-configured model names."""
    return list(EXPANSION_MODELS.keys())


def get_default_model() -> str:
    """Get the default expansion model name."""
    return DEFAULT_EXPANSION_MODEL


def get_default_model_config() -> ExpansionModelConfig:
    """Get the default expansion model configuration."""
    return EXPANSION_MODELS[DEFAULT_EXPANSION_MODEL]
