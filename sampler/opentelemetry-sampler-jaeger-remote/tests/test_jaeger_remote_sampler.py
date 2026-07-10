# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import gc
import sys
import threading
import weakref
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.sampler.jaeger.remote import (
    JaegerRemoteSampler,
    _create_provider,
)
from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
    SamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote._samplers import (
    PerOperationSampler,
    ProbabilisticSampler,
    RateLimitingSampler,
)

_ENDPOINT = "http://localhost:5778/sampling"
_SERVICE_NAME = "my-service"
_PATCH_TARGET = "opentelemetry.sampler.jaeger.remote._create_provider"


class _FakeProvider(SamplingStrategyProvider):
    def __init__(self, strategy):
        self.strategy = strategy
        self.call_count = 0
        self.fetched = threading.Semaphore(0)
        self.closed = False
        self.block_event: threading.Event | None = None

    def get_sampling_strategy(self, service_name):
        self.call_count += 1
        if self.block_event is not None:
            self.block_event.wait()
        strategy = self.strategy
        self.fetched.release()
        return strategy

    def close(self):
        self.closed = True


class TestCreateProvider(TestCase):
    def test_http_constructs_real_provider(self):
        provider = _create_provider("http", _ENDPOINT, None, None)
        self.addCleanup(provider.close)
        self.assertEqual(
            provider.__class__.__name__, "HttpSamplingStrategyProvider"
        )

    def test_grpc_constructs_real_provider(self):
        provider = _create_provider("grpc", "localhost:14250", None, None)
        self.addCleanup(provider.close)
        self.assertEqual(
            provider.__class__.__name__, "GrpcSamplingStrategyProvider"
        )

    def test_http_missing_extra_raises(self):
        with patch.dict(
            sys.modules,
            {"opentelemetry.sampler.jaeger.remote._http_provider": None},
        ):
            with self.assertRaises(ImportError) as ctx:
                _create_provider("http", _ENDPOINT, None, None)
        self.assertIn("[http]", str(ctx.exception))

    def test_grpc_missing_extra_raises(self):
        with patch.dict(
            sys.modules,
            {"opentelemetry.sampler.jaeger.remote._grpc_provider": None},
        ):
            with self.assertRaises(ImportError) as ctx:
                _create_provider("grpc", "localhost:14250", None, None)
        self.assertIn("[grpc]", str(ctx.exception))

    def test_unsupported_protocol_raises(self):
        with self.assertRaises(ValueError):
            _create_provider("bogus", _ENDPOINT, None, None)


class TestJaegerRemoteSampler(TestCase):
    def test_constructor_does_not_block(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=1.0))
        provider.block_event = threading.Event()
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(_ENDPOINT, _SERVICE_NAME)
        self.addCleanup(sampler.close)

        # The constructor must have returned already; the fake provider's
        # fetch is still blocked, so the initial default sampler is active.
        self.assertIsInstance(sampler._sampler, ProbabilisticSampler)
        self.assertEqual(sampler._sampler.rate, 0.001)

        provider.block_event.set()
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

    def test_default_initial_sampler(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=1.0))
        provider.block_event = threading.Event()
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(_ENDPOINT, _SERVICE_NAME)
        self.addCleanup(sampler.close)

        with sampler._lock:
            self.assertIsInstance(sampler._sampler, ProbabilisticSampler)
            self.assertEqual(sampler._sampler.rate, 0.001)

        provider.block_event.set()

    def test_custom_initial_sampler_until_fetch(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=1.0))
        provider.block_event = threading.Event()
        initial_sampler = RateLimitingSampler(3)
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, initial_sampler=initial_sampler
            )
        self.addCleanup(sampler.close)

        self.assertIs(sampler._sampler, initial_sampler)
        provider.block_event.set()

    def test_background_thread_fetches_immediately(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)

        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))
        self.assertEqual(provider.call_count, 1)
        self.assertIsInstance(sampler._sampler, ProbabilisticSampler)
        self.assertEqual(sampler._sampler.rate, 0.5)

    def test_close_stops_thread_and_provider(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        sampler.close()

        self.assertFalse(sampler._thread.is_alive())
        self.assertTrue(provider.closed)

    def test_close_is_idempotent(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        sampler.close()
        sampler.close()

    def test_del_after_close_does_not_raise(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        sampler.close()
        del sampler
        gc.collect()

        self.assertTrue(provider.closed)

    def test_deleting_sampler_stops_thread(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        thread = sampler._thread
        weak_sampler = weakref.ref(sampler)

        del sampler
        gc.collect()

        self.assertIsNone(weak_sampler())
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(provider.closed)

    def test_reuses_sampler_on_same_strategy_type(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        first_sampler = sampler._sampler
        self.assertIsInstance(first_sampler, ProbabilisticSampler)

        provider.strategy = ProbabilisticStrategy(sampling_rate=0.75)
        sampler._update_sampler()

        self.assertIs(sampler._sampler, first_sampler)
        self.assertEqual(sampler._sampler.rate, 0.75)

    def test_replaces_sampler_on_type_change(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        first_sampler = sampler._sampler
        self.assertIsInstance(first_sampler, ProbabilisticSampler)

        provider.strategy = RateLimitingStrategy(max_traces_per_second=5)
        sampler._update_sampler()

        self.assertIsNot(sampler._sampler, first_sampler)
        self.assertIsInstance(sampler._sampler, RateLimitingSampler)

    def test_default_max_operations_used(
        self,
    ):
        provider = _FakeProvider(
            PerOperationStrategy(
                default_sampling_probability=0.1,
                default_lower_bound_traces_per_second=0.0,
                operation_strategies=(
                    OperationStrategy(operation="op-a", sampling_rate=1.0),
                ),
            )
        )
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))

        self.assertIsInstance(sampler._sampler, PerOperationSampler)
        # pylint: disable-next=protected-access
        self.assertEqual(sampler._sampler._max_operations, 256)

    def test_fetch_failure_keeps_previous_sampler(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=0.5))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)
        # pylint: disable-next=consider-using-with
        self.assertTrue(provider.fetched.acquire(timeout=2))
        previous_sampler = sampler._sampler

        with patch.object(
            provider, "get_sampling_strategy", side_effect=RuntimeError
        ):
            sampler._update_sampler()

        self.assertIs(sampler._sampler, previous_sampler)

    def test_get_description(self):
        provider = _FakeProvider(ProbabilisticStrategy(sampling_rate=1.0))
        with patch(_PATCH_TARGET, return_value=provider):
            sampler = JaegerRemoteSampler(
                _ENDPOINT, _SERVICE_NAME, polling_interval=3600
            )
        self.addCleanup(sampler.close)
        self.assertIn("JaegerRemoteSampler{", sampler.get_description())
