"""LLM Client abstraction — supports OpenAI and any compatible provider."""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin async wrapper around an LLM provider."""

    def __init__(self) -> None:
        self._client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            if settings.llm_provider == "openai":
                try:
                    from openai import AsyncOpenAI
                    self._client = AsyncOpenAI(api_key=settings.llm_api_key)
                except ImportError:
                    raise RuntimeError("openai package not installed. Run: pip install openai")
            else:
                raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
        return self._client

    async def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Return the text completion for a system + user prompt pair."""
        client = self._get_client()
        chosen_model = model or settings.llm_model

        if settings.llm_provider == "openai":
            response = await client.chat.completions.create(
                model=chosen_model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content or ""

        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    async def complete_with_verifier(self, system: str, user: str) -> str:
        """Use the dedicated verifier model (may differ from generator)."""
        return await self.complete(
            system=system,
            user=user,
            model=settings.verifier_model,
        )


llm_client = LLMClient()
