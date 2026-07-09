# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

import urllib3.exceptions
from mocket import Mocket, Mocketizer
from mocket.mocks.mockhttp import Entry

from opentelemetry.sampler.jaeger.remote._http_provider import (
    _DEFAULT_TIMEOUT,
    HttpSamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
)

_ENDPOINT = "http://mock/sampling"

_PROBABILISTIC_BODY = (
    '{"strategyType": "PROBABILISTIC", '
    '"probabilisticSampling": {"samplingRate": 0.5}}'
)


def _register(*responses, match_querystring=False):
    Entry.register(
        Entry.GET, _ENDPOINT, *responses, match_querystring=match_querystring
    )


class _MocketTestCase(TestCase):
    def setUp(self):
        self.mocketizer = Mocketizer(strict_mode=True)
        self.mocketizer.enter()

    def tearDown(self):
        self.mocketizer.exit()


class TestConstructor(_MocketTestCase):
    def test_default_timeout(self):
        provider = HttpSamplingStrategyProvider(_ENDPOINT)
        self.assertEqual(provider._timeout, _DEFAULT_TIMEOUT)

    def test_explicit_timeout_and_headers(self):
        provider = HttpSamplingStrategyProvider(
            _ENDPOINT, headers={"Authorization": "Bearer secret"}, timeout=2.5
        )
        self.assertEqual(provider._timeout, 2.5)
        self.assertEqual(
            provider._pool.headers, {"Authorization": "Bearer secret"}
        )


class TestGetSamplingStrategy(_MocketTestCase):
    def test_sends_service_query_param_and_headers(self):
        _register(Entry.response_cls(body=_PROBABILISTIC_BODY, status=200))
        provider = HttpSamplingStrategyProvider(
            _ENDPOINT, headers={"X-Test": "yes"}
        )

        provider.get_sampling_strategy("my-service")

        request = Mocket.last_request()
        self.assertEqual(request.querystring, {"service": ["my-service"]})
        headers = {k.lower(): v for k, v in request.headers.items()}
        self.assertEqual(headers.get("x-test"), "yes")

    def test_probabilistic_strategy(self):
        _register(Entry.response_cls(body=_PROBABILISTIC_BODY, status=200))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))

    def test_rate_limiting_strategy(self):
        _register(
            Entry.response_cls(
                body=(
                    '{"strategyType": "RATE_LIMITING", '
                    '"rateLimitingSampling": {"maxTracesPerSecond": 5}}'
                ),
                status=200,
            )
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(
            strategy, RateLimitingStrategy(max_traces_per_second=5)
        )

    def test_per_operation_strategy(self):
        _register(
            Entry.response_cls(
                body=(
                    '{"operationSampling": {'
                    '"defaultSamplingProbability": 0.1,'
                    '"defaultLowerBoundTracesPerSecond": 1.0,'
                    '"defaultUpperBoundTracesPerSecond": 10.0,'
                    '"perOperationStrategies": [{'
                    '"operation": "op-a",'
                    '"probabilisticSampling": {"samplingRate": 0.75}'
                    "}]"
                    "}}"
                ),
                status=200,
            )
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(
            strategy,
            PerOperationStrategy(
                default_sampling_probability=0.1,
                default_lower_bound_traces_per_second=1.0,
                operation_strategies=(
                    OperationStrategy(operation="op-a", sampling_rate=0.75),
                ),
                default_upper_bound_traces_per_second=10.0,
            ),
        )

    def test_non_retryable_error_status_raises(self):
        _register(Entry.response_cls(status=404))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        with self.assertRaises(RuntimeError):
            provider.get_sampling_strategy("my-service")

    def test_retries_transient_error_then_succeeds(self):
        _register(
            Entry.response_cls(status=503),
            Entry.response_cls(body=_PROBABILISTIC_BODY, status=200),
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))

    def test_retries_exhausted_raises(self):
        _register(*(Entry.response_cls(status=503) for _ in range(6)))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        with self.assertRaises(urllib3.exceptions.MaxRetryError):
            provider.get_sampling_strategy("my-service")


class TestClose(_MocketTestCase):
    def test_close_clears_pool(self):
        _register(Entry.response_cls(body=_PROBABILISTIC_BODY, status=200))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)
        provider.get_sampling_strategy("my-service")
        self.assertGreater(len(provider._pool.pools), 0)

        provider.close()

        self.assertEqual(len(provider._pool.pools), 0)
