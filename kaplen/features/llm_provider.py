"""
features/llm_provider.py
Provider-agnostic LLM interface.

Supported providers (set via LLM_PROVIDER env var):
    anthropic  — Anthropic Claude  (default)
    openai     — OpenAI / any OpenAI-compatible endpoint

Environment variables
---------------------
LLM_PROVIDER      Provider name (default: anthropic)
LLM_API_KEY       API key — falls back to ANTHROPIC_API_KEY or OPENAI_API_KEY
LLM_MODEL         Model ID — falls back to ANTHROPIC_MODEL or OPENAI_MODEL
LLM_BASE_URL      Optional base URL for OpenAI-compatible endpoints
"""

import os
import logging

logger = logging.getLogger(__name__)


class LLMProvider:
    """Abstract LLM provider. Subclass and implement complete()."""

    def complete(self, messages: list[dict], max_tokens: int = 2000) -> str:
        raise NotImplementedError

    def stream_complete(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        on_token: callable = None,
    ) -> str:
        """
        Complete with an optional per-token callback.
        Falls back to complete() if streaming is not implemented.
        Returns the full accumulated text.
        """
        text = self.complete(messages, max_tokens)
        if on_token:
            on_token(text)
        return text

    @property
    def model_name(self) -> str:
        return getattr(self, '_model', 'unknown')


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, model: str):
        import anthropic as _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, messages: list[dict], max_tokens: int = 2000) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.content[0].text

    def stream_complete(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        on_token: callable = None,
    ) -> str:
        content = ""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                content += text
                if on_token:
                    on_token(text)
        return content


class OpenAIProvider(LLMProvider):
    """OpenAI (or any OpenAI-compatible) provider."""

    def __init__(self, api_key: str, model: str, base_url: str = None):
        import openai as _openai
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = _openai.OpenAI(**kwargs)
        self._model = model

    def complete(self, messages: list[dict], max_tokens: int = 2000) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content

    def stream_complete(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        on_token: callable = None,
    ) -> str:
        content = ""
        stream = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            text = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            content += text
            if on_token and text:
                on_token(text)
        return content


def get_provider() -> LLMProvider:
    """
    Build an LLMProvider from environment variables.

    LLM_PROVIDER=anthropic  →  AnthropicProvider
                             uses LLM_API_KEY  (fallback: ANTHROPIC_API_KEY)
                             uses LLM_MODEL    (fallback: ANTHROPIC_MODEL → claude-sonnet-4-6)

    LLM_PROVIDER=openai     →  OpenAIProvider
                             uses LLM_API_KEY  (fallback: OPENAI_API_KEY)
                             uses LLM_MODEL    (fallback: OPENAI_MODEL → gpt-4o)
                             uses LLM_BASE_URL (optional, for compatible endpoints)
    """
    name = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()

    if name == "anthropic":
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY", "")
        )
        model = (
            os.getenv("LLM_MODEL")
            or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        )
        logger.info(f"LLM provider: Anthropic / {model}")
        return AnthropicProvider(api_key, model)

    if name == "openai":
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        )
        model = (
            os.getenv("LLM_MODEL")
            or os.getenv("OPENAI_MODEL", "gpt-4o")
        )
        base_url = os.getenv("LLM_BASE_URL")
        logger.info(f"LLM provider: OpenAI-compatible / {model}")
        return OpenAIProvider(api_key, model, base_url)

    raise ValueError(
        f"Unknown LLM_PROVIDER={name!r}. "
        "Supported values: anthropic, openai"
    )
