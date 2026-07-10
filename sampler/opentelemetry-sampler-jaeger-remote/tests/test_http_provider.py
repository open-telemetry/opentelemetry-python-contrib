# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import urllib3.exceptions
from mocket import Mocket, Mocketizer
from mocket.mocks.mockhttp import Entry

from opentelemetry.sampler.jaeger.remote._http_provider import (
    _DEFAULT_TIMEOUT,
    _MAX_RETRIES,
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

_SLEEP_TARGET = "opentelemetry.sampler.jaeger.remote._http_provider.time.sleep"
_MONOTONIC_TARGET = (
    "opentelemetry.sampler.jaeger.remote._http_provider.time.monotonic"
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
    def test_sends_service_param_and_headers(self):
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

    @patch(_SLEEP_TARGET)
    def test_non_retryable_error_status_raises(self, mock_sleep):
        _register(Entry.response_cls(status=404))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        with self.assertRaises(RuntimeError):
            provider.get_sampling_strategy("my-service")

        mock_sleep.assert_not_called()

    @patch(_SLEEP_TARGET)
    def test_retries_then_succeeds(self, mock_sleep):
        _register(
            Entry.response_cls(status=503),
            Entry.response_cls(body=_PROBABILISTIC_BODY, status=200),
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))
        mock_sleep.assert_called_once()

    @patch(_SLEEP_TARGET)
    def test_retries_exhausted_raises(self, mock_sleep):
        _register(
            *(Entry.response_cls(status=503) for _ in range(_MAX_RETRIES + 1))
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        with self.assertRaises(RuntimeError):
            provider.get_sampling_strategy("my-service")

        self.assertEqual(mock_sleep.call_count, _MAX_RETRIES)

    @patch(_SLEEP_TARGET)
    def test_retries_transport_error(self, mock_sleep):
        _register(
            urllib3.exceptions.ProtocolError("connection broken"),
            Entry.response_cls(body=_PROBABILISTIC_BODY, status=200),
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))
        mock_sleep.assert_called_once()

    @patch(_SLEEP_TARGET)
    def test_transport_errors_exhausted_raises(self, mock_sleep):
        _register(
            *(
                urllib3.exceptions.ProtocolError("connection broken")
                for _ in range(_MAX_RETRIES + 1)
            )
        )
        provider = HttpSamplingStrategyProvider(_ENDPOINT)

        with self.assertRaises(RuntimeError):
            provider.get_sampling_strategy("my-service")

        self.assertEqual(mock_sleep.call_count, _MAX_RETRIES)

    @patch(_SLEEP_TARGET)
    @patch(_MONOTONIC_TARGET)
    def test_retry_uses_remaining_deadline(
        self, mock_monotonic, mock_sleep
    ):
        # 1 call for the initial deadline, then per attempt: 1 before the
        # call (used as its timeout) and, on failure, 1 more right after to
        # check the deadline before deciding to retry. Attempt 0 fails at
        # t=0/t=0; attempt 1 (t=3) then succeeds.
        mock_monotonic.side_effect = [0, 0, 0, 3]
        provider = HttpSamplingStrategyProvider(_ENDPOINT, timeout=10)
        responses = [
            urllib3.exceptions.ProtocolError("connection broken"),
            SimpleNamespace(status=200, data=_PROBABILISTIC_BODY.encode()),
        ]
        with patch.object(
            provider._pool, "request", side_effect=responses
        ) as mock_request:
            strategy = provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))
        self.assertEqual(mock_request.call_args_list[0].kwargs["timeout"], 10)
        self.assertEqual(mock_request.call_args_list[1].kwargs["timeout"], 7)
        mock_sleep.assert_called_once()

    @patch(_SLEEP_TARGET)
    @patch(_MONOTONIC_TARGET)
    def test_deadline_exceeded_raises_early(
        self, mock_monotonic, mock_sleep
    ):
        # Deadline (t=10) has already passed by the time the post-failure
        # check for attempt 0 runs (t=15), well before _MAX_RETRIES (3) and
        # before ever sleeping/retrying.
        mock_monotonic.side_effect = [0, 0, 15]
        provider = HttpSamplingStrategyProvider(_ENDPOINT, timeout=10)
        error = urllib3.exceptions.ProtocolError("connection broken")
        with patch.object(
            provider._pool, "request", side_effect=[error]
        ) as mock_request:
            with self.assertRaises(RuntimeError) as ctx:
                provider.get_sampling_strategy("my-service")

        self.assertIn("connection broken", str(ctx.exception))
        self.assertEqual(mock_request.call_count, 1)
        mock_sleep.assert_not_called()


class TestClose(_MocketTestCase):
    def test_close_clears_pool(self):
        _register(Entry.response_cls(body=_PROBABILISTIC_BODY, status=200))
        provider = HttpSamplingStrategyProvider(_ENDPOINT)
        provider.get_sampling_strategy("my-service")
        self.assertGreater(len(provider._pool.pools), 0)

        provider.close()

        self.assertEqual(len(provider._pool.pools), 0)
