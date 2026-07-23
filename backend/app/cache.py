import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class AsyncTTLCache:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: int,
    ) -> Any:
        now = monotonic()
        entry = self._entries.get(key)
        if entry and entry.expires_at > now:
            return entry.value

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = monotonic()
            entry = self._entries.get(key)
            if entry and entry.expires_at > now:
                return entry.value

            value = await factory()
            self._entries[key] = CacheEntry(value, now + ttl)
            return value

