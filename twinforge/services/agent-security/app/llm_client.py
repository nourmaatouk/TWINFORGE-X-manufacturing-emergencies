"""
LLM Client - Wrapper for GitHub Models API (OpenAI o3).

Provides async LLM calls for security analysis that goes beyond regex patterns.
Used by detectors when rule-based checks are inconclusive and deeper
semantic analysis is needed. Also powers the rethinking loop.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Models that use max_completion_tokens instead of max_tokens
REASONING_MODELS = {"openai/o3", "openai/o3-mini", "openai/o1", "openai/o1-mini", "openai/o1-preview"}


class LLMClient:
    """
    Async client for GitHub Models API.
    Supports both standard models (GPT-4o) and reasoning models (o3).
    """

    def __init__(self):
        self.endpoint = settings.GITHUB_MODELS_ENDPOINT
        self.model = settings.GITHUB_MODEL
        self.token = settings.GITHUB_TOKEN
        self._client = httpx.AsyncClient(timeout=60.0)

    @property
    def is_configured(self) -> bool:
        """Check if the LLM client has a valid token configured."""
        return bool(self.token)

    @property
    def is_reasoning_model(self) -> bool:
        """Check if the configured model is a reasoning model (o3, o1, etc.)."""
        return self.model in REASONING_MODELS

    async def analyze(self, system_prompt: str, user_content: str, max_tokens: int = 300) -> dict[str, Any]:
        """
        Send a security analysis prompt to the configured LLM.

        Args:
            system_prompt: The system instruction for the model.
            user_content: The content to analyze.
            max_tokens: Max response tokens.

        Returns:
            dict with 'success', 'content' (the model reply), and optional 'error'.
        """
        if not self.is_configured:
            return {"success": False, "content": "", "error": "No GITHUB_TOKEN configured"}

        try:
            # Build messages - reasoning models use developer role instead of system
            if self.is_reasoning_model:
                messages = [
                    {"role": "developer", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]

            # Build request body - reasoning models use different token param
            body: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
            }

            if self.is_reasoning_model:
                body["max_completion_tokens"] = max_tokens
            else:
                body["max_tokens"] = max_tokens
                body["temperature"] = 0.1

            resp = await self._client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return {"success": True, "content": content}
            else:
                logger.error(f"LLM API returned {resp.status_code}: {resp.text[:200]}")
                return {"success": False, "content": "", "error": f"API error {resp.status_code}"}

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {"success": False, "content": "", "error": str(e)}


# Singleton instance
llm_client = LLMClient()
