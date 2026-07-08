# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from threading import Thread
from unittest import TestCase

from opentelemetry.sampler.jaeger.remote._ratelimiter import RateLimiter


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestRateLimiter(TestCase):
    def test_starts_at_full_balance(self):
        clock = _FakeClock()
        limiter = RateLimiter(1, 5, clock=clock)

        for _ in range(5):
            self.assertTrue(limiter.try_spend(1))
        self.assertFalse(limiter.try_spend(1))

    def test_max_balance_defaults_to_credits_per_second(self):
        clock = _FakeClock()
        limiter = RateLimiter(3, clock=clock)

        for _ in range(3):
            self.assertTrue(limiter.try_spend(1))
        self.assertFalse(limiter.try_spend(1))

    def test_update_max_balance_defaults_to_credits_per_second(self):
        clock = _FakeClock()
        # Starts full (balance == max_balance == 10).
        limiter = RateLimiter(0, 10, clock=clock)

        # Rescales the full balance down to the new max_balance (4).
        limiter.update(4)
        for _ in range(4):
            self.assertTrue(limiter.try_spend(1))
        self.assertFalse(limiter.try_spend(1))

    def test_refill_over_time(self):
        clock = _FakeClock()
        limiter = RateLimiter(10, 5, clock=clock)

        for _ in range(5):
            self.assertTrue(limiter.try_spend(1))
        self.assertFalse(limiter.try_spend(1))

        clock.advance(0.5)
        for _ in range(5):
            self.assertTrue(limiter.try_spend(1))
        self.assertFalse(limiter.try_spend(1))

    def test_balance_caps_at_max_balance(self):
        clock = _FakeClock()
        limiter = RateLimiter(10, 5, clock=clock)

        for _ in range(5):
            self.assertTrue(limiter.try_spend(1))

        clock.advance(1000)
        spent = 0
        for _ in range(100):
            if limiter.try_spend(1):
                spent += 1
        self.assertEqual(spent, 5)

    def test_fractional_cost(self):
        clock = _FakeClock()
        limiter = RateLimiter(1, 1, clock=clock)

        self.assertTrue(limiter.try_spend(0.5))
        self.assertTrue(limiter.try_spend(0.5))
        self.assertFalse(limiter.try_spend(0.5))

    def test_insufficient_balance_leaves_balance_unchanged(self):
        clock = _FakeClock()
        limiter = RateLimiter(1, 1, clock=clock)

        self.assertTrue(limiter.try_spend(0.75))
        # Not enough balance left (0.25) for this spend.
        self.assertFalse(limiter.try_spend(0.5))
        # The failed attempt above must not have touched the balance.
        self.assertTrue(limiter.try_spend(0.25))

    def test_update_rescales_balance_proportionally(self):
        clock = _FakeClock()
        limiter = RateLimiter(0, 10, clock=clock)

        # Spend half the balance, then double the capacity - the remaining
        # balance should scale up proportionally rather than resetting.
        self.assertTrue(limiter.try_spend(5))
        limiter.update(0, 20)
        self.assertTrue(limiter.try_spend(10))
        self.assertFalse(limiter.try_spend(1))

    def test_update_rejects_invalid_arguments(self):
        limiter = RateLimiter(1, 1, clock=_FakeClock())

        with self.assertRaises(ValueError):
            limiter.update(-1, 1)
        with self.assertRaises(ValueError):
            limiter.update(1, 0)

    def test_constructor_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            RateLimiter(-1, 1)
        with self.assertRaises(ValueError):
            RateLimiter(1, 0)
        with self.assertRaises(ValueError):
            RateLimiter(1, -1)

    def test_concurrent_try_spend_is_thread_safe(self):
        clock = _FakeClock()
        max_balance = 50
        limiter = RateLimiter(0, max_balance, clock=clock)

        successes = []

        def spend() -> None:
            if limiter.try_spend(1):
                successes.append(1)

        threads = [Thread(target=spend) for _ in range(500)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(successes), max_balance)
