"""OpenAI-compatible chat client. In production it points at Sluice, which routes,
caches and falls back across free providers; any OpenAI-compatible endpoint works."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass
class Completion:
    text: str
    model: str
    ms: float
    cache: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class LLMError(Exception):
    pass


class LLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            transport=transport,
        )

    async def chat(self, messages: list[dict], temperature: float = 0.0, max_tokens: int = 700) -> Completion:
        t = time.perf_counter()
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        for attempt in range(3):
            try:
                r = await self._client.post(f"{self.base_url}/chat/completions", json=body)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise LLMError(f"LLM unreachable: {e.__class__.__name__}") from e
                continue
            if r.status_code == 429 and attempt < 2:
                await _sleep(2 + 4 * attempt)
                continue
            if r.status_code >= 400:
                try:
                    msg = r.json()["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    msg = r.text[:200]
                raise LLMError(f"LLM error {r.status_code}: {msg}")
            data = r.json()
            meta = data.get("sluice") or {}
            usage = data.get("usage") or {}
            return Completion(
                text=data["choices"][0]["message"].get("content") or "",
                model=meta.get("served_by") or data.get("model", self.model),
                ms=(time.perf_counter() - t) * 1000,
                cache=meta.get("cache"),
                tokens_in=int(usage.get("prompt_tokens") or 0),
                tokens_out=int(usage.get("completion_tokens") or 0),
            )
        raise LLMError("LLM rate limited")

    async def aclose(self) -> None:
        await self._client.aclose()


async def _sleep(s: float) -> None:
    import asyncio

    await asyncio.sleep(s)
