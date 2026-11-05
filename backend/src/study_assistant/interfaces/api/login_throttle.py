"""Slows password guessing: too many wrong passwords from one client locks that client out.

State is in memory, which suits a single server process. A restart clears it.
"""

import math
import threading
import time
from collections.abc import Callable


class FailedLoginThrottle:
    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        """``max_clients`` bounds memory; past it, the oldest client's record is dropped."""
        self._max_failures = max_failures
        self._window = window_seconds
        self._clock = clock
        self._max_clients = max_clients
        self._failures: dict[str, tuple[int, float]] = {}  # client -> (count, window end)
        self._lock = threading.Lock()  # routes run in a thread pool

    def retry_after(self, client: str) -> int | None:
        """Whole seconds until ``client`` may try again, or None if it isn't locked out."""
        now = self._clock()
        with self._lock:
            count, ends_at = self._failures.get(client, (0, now))
            if count < self._max_failures or ends_at <= now:
                return None
            return math.ceil(ends_at - now)

    def record_failure(self, client: str) -> None:
        now = self._clock()
        with self._lock:
            self._failures = {k: v for k, v in self._failures.items() if v[1] > now}
            count, ends_at = self._failures.pop(client, (0, now + self._window))
            self._failures[client] = (count + 1, ends_at)
            if len(self._failures) > self._max_clients:
                del self._failures[next(iter(self._failures))]

    def clear(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)
