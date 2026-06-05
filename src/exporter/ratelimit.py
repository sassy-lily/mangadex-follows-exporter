"""A small thread-safe token-bucket rate limiter.

MangaDex enforces a global ~5 req/s limit; the batched id-fetches here can fire
many requests in quick succession, so a single shared limiter is threaded
through the client to keep us under the cap regardless of which endpoint is
being called.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Token bucket allowing at most ``rate`` operations per second.

    ``acquire`` blocks until a token is available. A small ``burst`` lets a
    handful of calls go out immediately before throttling kicks in.
    """

    def __init__(self, rate: float, burst: int | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._capacity = float(burst if burst is not None else max(1, int(rate)))
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated
                self._updated = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Wait just long enough for the next token to accrue.
                deficit = 1.0 - self._tokens
                time.sleep(deficit / self._rate)
