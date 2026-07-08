# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from threading import Lock
from typing import Callable


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(
        self,
        credits_per_second: float,
        max_balance: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_balance is None:
            max_balance = credits_per_second
        if credits_per_second < 0:
            raise ValueError("credits_per_second must be non-negative")
        if max_balance <= 0:
            raise ValueError("max_balance must be positive")

        self._credits_per_second = credits_per_second
        self._max_balance = max_balance
        self._clock = clock
        self._balance = max_balance
        self._last_tick = clock()
        self._lock = Lock()

    def try_spend(self, cost: float = 1.0) -> bool:
        """Attempt to withdraw `cost` credits from the balance.

        Returns:
            True if the balance had enough credits and they were withdrawn,
            False otherwise (balance is left unchanged).
        """
        with self._lock:
            self._refill_locked()
            if self._balance < cost:
                return False
            self._balance -= cost
            return True

    def update(
        self, credits_per_second: float, max_balance: float | None = None
    ) -> None:
        """Reconfigure the rate/capacity in place.

        The current balance is rescaled proportionally to the new
        `max_balance` rather than being reset, so an in-progress bucket
        doesn't lose or gain credits purely as a result of reconfiguration.
        """
        if max_balance is None:
            max_balance = credits_per_second
        if credits_per_second < 0:
            raise ValueError("credits_per_second must be non-negative")
        if max_balance <= 0:
            raise ValueError("max_balance must be positive")

        with self._lock:
            self._refill_locked()
            self._balance = max_balance * self._balance / self._max_balance
            self._credits_per_second = credits_per_second
            self._max_balance = max_balance

    def _refill_locked(self) -> None:
        """Refill the balance based on elapsed time. Caller must hold `_lock`."""
        now = self._clock()
        elapsed = now - self._last_tick
        self._last_tick = now
        self._balance = min(
            self._max_balance,
            self._balance + elapsed * self._credits_per_second,
        )
