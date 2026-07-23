import asyncio
from collections import deque
from time import monotonic
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        per_second: int,
        per_minute: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.per_second = per_second
        self.per_minute = per_minute
        self._clock = clock
        self._requests: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = self._clock()
                self._discard_expired(now)
                recent_second = sum(now - item < 1 for item in self._requests)

                waits: list[float] = []
                if recent_second >= self.per_second:
                    second_window = [
                        item for item in self._requests if now - item < 1
                    ]
                    waits.append(1 - (now - second_window[0]))
                if len(self._requests) >= self.per_minute:
                    waits.append(60 - (now - self._requests[0]))

                if not waits:
                    self._requests.append(now)
                    return

                wait_for = max(0.01, max(waits))

            await asyncio.sleep(wait_for)

    def _discard_expired(self, now: float) -> None:
        while self._requests and now - self._requests[0] >= 60:
            self._requests.popleft()

