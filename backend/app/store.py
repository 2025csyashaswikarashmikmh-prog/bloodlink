"""Tiny key-value store with TTL: Redis when REDIS_URL is set, otherwise in-memory.
Used for OTPs, rate limits and voice-assistant session state."""
from __future__ import annotations

import json
import time

from .config import settings


class _MemoryStore:
    def __init__(self):
        self._d: dict[str, tuple[float, str]] = {}

    def set(self, key: str, value, ttl: int = 600):
        self._d[key] = (time.time() + ttl, json.dumps(value))

    def get(self, key: str):
        item = self._d.get(key)
        if not item:
            return None
        exp, val = item
        if exp < time.time():
            self._d.pop(key, None)
            return None
        return json.loads(val)

    def delete(self, key: str):
        self._d.pop(key, None)

    def incr(self, key: str, ttl: int = 60) -> int:
        cur = self.get(key) or 0
        self.set(key, cur + 1, ttl)
        return cur + 1

    @property
    def backend(self):
        return "memory"


class _RedisStore(_MemoryStore):
    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        self.r.ping()

    def set(self, key, value, ttl=600):
        self.r.set(key, json.dumps(value), ex=ttl)

    def get(self, key):
        v = self.r.get(key)
        return json.loads(v) if v else None

    def delete(self, key):
        self.r.delete(key)

    def incr(self, key, ttl=60):
        n = self.r.incr(key)
        if n == 1:
            self.r.expire(key, ttl)
        return n

    @property
    def backend(self):
        return "redis"


def _make():
    if settings.REDIS_URL:
        try:
            return _RedisStore(settings.REDIS_URL)
        except Exception as e:  # pragma: no cover - fallback path
            print(f"[store] Redis unavailable ({e}); using in-memory store")
    return _MemoryStore()


store = _make()
