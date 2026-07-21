"""Circuit breaker for AI provider calls.

Prevents cascading failures by opening the circuit after *N*
consecutive failures, then allowing a recovery probe after a
configurable timeout.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple state-machine circuit breaker.

    States
    ------
    *closed*
        Normal operation — all calls pass through.
    *open*
        Calls are rejected immediately with ``RuntimeError``.
    *half-open*
        Transitional state after ``recovery_timeout`` seconds in
        *open* — the next call is allowed as a probe.

    The circuit resets to *closed* on any successful call.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time = 0.0
        self._state = "closed"

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        if self._state == "open" and (
            time.monotonic() - self._last_failure_time
        ) > self._recovery_timeout:
            self._state = "half-open"
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # ------------------------------------------------------------------
    # Main guard
    # ------------------------------------------------------------------

    def call(self, fn, *args, **kwargs):
        """Execute *fn* with circuit-breaker protection.

        Raises
        ------
        RuntimeError
            When the circuit is **open** — the AI provider is known
            to be unhealthy and the call is rejected immediately.
        """
        if self.state == "open":
            raise RuntimeError(
                "Circuit breaker is OPEN — not calling AI provider"
            )
        try:
            result = fn(*args, **kwargs)
            self._failure_count = 0
            self._state = "closed"
            return result
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                logger.critical(
                    "Circuit breaker opened after %d failures",
                    self._failure_count,
                )
            raise

    async def call_async(self, fn, *args, **kwargs):
        """Async variant of :meth:`call`."""
        if self.state == "open":
            raise RuntimeError(
                "Circuit breaker is OPEN — not calling AI provider"
            )
        try:
            result = await fn(*args, **kwargs)
            self._failure_count = 0
            self._state = "closed"
            return result
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                logger.critical(
                    "Circuit breaker opened after %d failures",
                    self._failure_count,
                )
            raise

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Manually reset the breaker to *closed*."""
        self._failure_count = 0
        self._state = "closed"
