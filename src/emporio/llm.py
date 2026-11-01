"""Thin DeepSeek chat-completions client (OpenAI-compatible tool calling)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


class LLMError(RuntimeError):
    """Provider failure. `retryable` distinguishes a transient 5xx/429 from a fatal 4xx."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any]
    model: str


class DeepSeekClient:
    """Provider-agnostic by construction: base_url + model come from config (ADR 0002)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        timeout: float = 90.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")
                if response.status_code >= 400:
                    # 4xx means the request itself is wrong (bad schema, bad key): retrying cannot help.
                    raise LLMError(
                        f"HTTP {response.status_code}: {response.text[:400]}", retryable=False
                    )
                data = response.json()
                message = data["choices"][0]["message"]
                return LLMResponse(
                    content=message.get("content") or "",
                    tool_calls=message.get("tool_calls") or [],
                    usage=data.get("usage", {}),
                    model=data.get("model", self.model),
                )
            except LLMError as exc:
                last_error = exc
                if not exc.retryable or attempt == self.max_retries - 1:
                    break
                time.sleep(1.5 * (attempt + 1))
            except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"falha ao chamar o provedor após {self.max_retries} tentativas: {last_error}")
