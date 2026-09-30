"""Fixed-window rate limits: Upstash Redis over REST in production, in memory locally."""

from __future__ import annotations

import time

import httpx


class Limiter:
    def __init__(self, url: str = "", token: str = ""):
        self._url = url.rstrip("/")
        self._client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=5.0) if url else None
        self._mem: dict[str, tuple[int, float]] = {}

    async def hit(self, name: str, limit: int, window_s: int) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, seconds until reset)."""
        now = int(time.time())
        bucket = now // window_s
        key = f"quarry:rl:{name}:{window_s}:{bucket}"
        reset = (bucket + 1) * window_s - now
        if self._client:
            try:
                r = await self._client.post(
                    f"{self._url}/pipeline", json=[["INCR", key], ["EXPIRE", key, str(window_s + 5)]]
                )
                count = int(r.json()[0]["result"])
            except (httpx.HTTPError, KeyError, ValueError, IndexError):
                return True, limit, reset  # fail open: a limiter outage should not take the demo down
        else:
            count = self._mem.get(key, (0, 0))[0] + 1
            self._mem[key] = (count, now + window_s)
        return count <= limit, max(0, limit - count), reset
