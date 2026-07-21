"""
Simple in-memory sliding-window rate limiter.

Used as a FastAPI middleware or dependency to protect endpoints from
excessive requests.  Uses a per-key (typically client IP) list of
timestamps to enforce a max-requests-per-window policy.

.. warning::
    This is a **single-process, in-memory** limiter.  It does **not**
    share state across multiple uvicorn workers or container replicas.
    For distributed deployments, replace this with Redis-based rate
    limiting (e.g. ``slowapi`` or a custom Redis-backed implementation).
"""

import time
from collections import defaultdict


class InMemoryRateLimiter:
    """Sliding-window rate limiter per key (e.g. client IP).

    Parameters
    ----------
    default_max_requests:
        Maximum number of requests allowed in the window (default 100).
    default_window_seconds:
        Width of the sliding window in seconds (default 60).
    """

    def __init__(
        self,
        default_max_requests: int = 100,
        default_window_seconds: int = 60,
    ):
        self._default_max = default_max_requests
        self._default_window = default_window_seconds
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def check(
        self,
        key: str,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> tuple[bool, int]:
        """Check whether *key* is within its rate limit.

        Parameters
        ----------
        key:
            Unique identifier for the client (e.g. ``"ip:1.2.3.4"``).
        max_requests:
            Override the default max requests for this check.
        window_seconds:
            Override the default window width for this check.

        Returns
        -------
        (allowed, current_count)
            ``allowed`` is ``True`` when the request should be let through,
            ``False`` when the limit has been exceeded.
            ``current_count`` is the number of requests seen in the current
            window (useful for ``X-RateLimit-Current`` headers).
        """
        now = time.time()
        max_r = max_requests or self._default_max
        window = window_seconds or self._default_window

        # Prune entries older than the window
        hits = self._windows[key]
        self._windows[key] = [t for t in hits if now - t < window]

        # Check limit
        if len(self._windows[key]) >= max_r:
            return False, len(self._windows[key])

        # Record this request
        self._windows[key].append(now)
        return True, len(self._windows[key])

    def cleanup(self, max_age: int = 300) -> int:
        """Remove stale entries older than *max_age* seconds.

        Call periodically (e.g. via a background task or cron) to prevent
        unbounded memory growth.  Returns the number of keys cleaned.
        """
        now = time.time()
        stale_keys = [
            k
            for k, timestamps in self._windows.items()
            if now - timestamps[-1] > max_age
        ]
        for k in stale_keys:
            del self._windows[k]
        return len(stale_keys)


# Singleton instance — import this in middleware / dependencies
rate_limiter = InMemoryRateLimiter()
