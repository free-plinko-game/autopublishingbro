"""OpenAI API wrapper for content generation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for the LLM client."""

    api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 2000
    temperature: float = 0.7
    base_url: str | None = None  # For OpenAI-compatible APIs

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Load configuration from environment variables."""
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", "gpt-4o"),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )


class LLMClient:
    """Wrapper around the OpenAI API for generating content.

    Handles API communication and provides a simple generate() interface.
    Supports any OpenAI-compatible API via base_url override.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()

        if not self.config.api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. Provide it via environment variable "
                "or pass LLMConfig with api_key."
            )

        client_kwargs: dict = {"api_key": self.config.api_key}
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        self._client = OpenAI(**client_kwargs)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text content using the LLM.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: The specific content request.
            max_tokens: Override default max_tokens.
            temperature: Override default temperature.

        Returns:
            Generated text content.

        Raises:
            LLMError: If the API call fails.
        """
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=temperature if temperature is not None else self.config.temperature,
            )

            content = response.choices[0].message.content or ""

            logger.debug(
                "LLM response: model=%s, tokens=%s",
                response.model,
                response.usage.total_tokens if response.usage else "unknown",
            )

            return content.strip()

        except Exception as e:
            raise LLMError(f"LLM API call failed: {e}") from e


class LLMError(Exception):
    """Raised when the LLM API call fails."""
