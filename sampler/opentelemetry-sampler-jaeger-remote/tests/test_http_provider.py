# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import http
import json
import socket
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import urllib3.exceptions
from mocket import Mocket, Mocketizer
from mocket.mocks.mockhttp import Entry

from opentelemetry.sampler.jaeger.remote._http_provider import (
    _DEFAULT_TIMEOUT,
    _MAX_RETRIES,
    _RETRYABLE_CONNECTION_ERRORS,
    _RETRYABLE_STATUSES,
    HttpSamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
)

_ENDPOINT = "http://mock/sampling"

_PROBABILISTIC_BODY = json.dumps(
    {
        "strategyType": "PROBABILISTIC",
        "probabilisticSampling": {"samplingRate": 0.5},
    }
)

_NON_RETRYABLE_STATUSES = tuple(
    sorted(
        status.value
        for status in http.HTTPStatus
        if status not in (http.HTTPStatus.OK, http.HTTPStatus.CONTINUE)
        and status.value not in _RETRYABLE_STATUSES
    )
)

_SLEEP_TARGET = "opentelemetry.sampler.jaeger.remote._http_provider.time.sleep"
_MONOTONIC_TARGET = (
    "opentelemetry.sampler.jaeger.remote._http_provider.time.monotonic"
)
_RANDOM_TARGET = (
    "opentelemetry.sampler.jaeger.remote._http_provider.random.uniform"
)


def _register(*responses, match_querystring=False):
    Entry.register(
        Entry.GET, _ENDPOINT, *responses, match_querystring=match_querystring
    )


def _make_connection_error(
    error_type: type[Exception],
) -> Exception:
    """Build a constructible instance of a urllib3 connection error type."""
    if error_type is urllib3.exceptions.MaxRetryError:
        return error_type(
            None, _ENDPOINT, reason=Exception("connection broken")
        )
    if error_type is getattr(urllib3.exceptions, "NameResolutionError", None):
        return error_type("mock", None, socket.gaierror("connection broken"))
    if error_type is urllib3.exceptions.NewConnectionError:
        return error_type(None, "connection broken")
    if error_type is urllib3.exceptions.ReadTimeoutError:
        return error_type(None, _ENDPOINT, "Read timed out.")
    return error_type("connection broken")


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

    def test_decodes_strategy_response(self):
        cases = {
            "probabilistic": (
                _PROBABILISTIC_BODY,
                ProbabilisticStrategy(sampling_rate=0.5),
            ),
            "rate_limiting": (
                json.dumps(
                    {
                        "strategyType": "RATE_LIMITING",
                        "rateLimitingSampling": {"maxTracesPerSecond": 5},
                    }
                ),
                RateLimitingStrategy(max_traces_per_second=5),
            ),
            "per_operation": (
                json.dumps(
                    {
                        "operationSampling": {
                            "defaultSamplingProbability": 0.1,
                            "defaultLowerBoundTracesPerSecond": 1.0,
                            "defaultUpperBoundTracesPerSecond": 10.0,
                            "perOperationStrategies": [
                                {
                                    "operation": "op-a",
                                    "probabilisticSampling": {
                                        "samplingRate": 0.75
                                    },
                                }
                            ],
                        }
                    }
                ),
                PerOperationStrategy(
                    default_sampling_probability=0.1,
                    default_lower_bound_traces_per_second=1.0,
                    operation_strategies=(
                        OperationStrategy(
                            operation="op-a", sampling_rate=0.75
                        ),
                    ),
                    default_upper_bound_traces_per_second=10.0,
                ),
            ),
        }
        for description, (body, expected) in cases.items():
            with self.subTest(description):
                Mocket.reset()
                _register(Entry.response_cls(body=body, status=200))
                provider = HttpSamplingStrategyProvider(_ENDPOINT)

                strategy = provider.get_sampling_strategy("my-service")

                self.assertEqual(strategy, expected)

    @patch(_SLEEP_TARGET)
    def test_non_retryable_error_status_raises(self, mock_sleep):
        for status in _NON_RETRYABLE_STATUSES:
            with self.subTest(status=status):
                Mocket.reset()
                _register(Entry.response_cls(status=status))
                provider = HttpSamplingStrategyProvider(_ENDPOINT)

                with self.assertRaises(RuntimeError):
                    provider.get_sampling_strategy("my-service")

        mock_sleep.assert_not_called()

    @patch(_SLEEP_TARGET)
    def test_retries_then_succeeds(self, mock_sleep):
        for status in sorted(_RETRYABLE_STATUSES):
            with self.subTest(status=status):
                Mocket.reset()
                mock_sleep.reset_mock()
                _register(
                    Entry.response_cls(status=status),
                    Entry.response_cls(body=_PROBABILISTIC_BODY, status=200),
                )
                provider = HttpSamplingStrategyProvider(_ENDPOINT)

                strategy = provider.get_sampling_strategy("my-service")

                self.assertEqual(
                    strategy, ProbabilisticStrategy(sampling_rate=0.5)
                )
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
        for error_type in dict.fromkeys(_RETRYABLE_CONNECTION_ERRORS):
            with self.subTest(error_type.__name__):
                Mocket.reset()
                mock_sleep.reset_mock()
                _register(
                    _make_connection_error(error_type),
                    Entry.response_cls(body=_PROBABILISTIC_BODY, status=200),
                )
                provider = HttpSamplingStrategyProvider(_ENDPOINT)

                strategy = provider.get_sampling_strategy("my-service")

                self.assertEqual(
                    strategy, ProbabilisticStrategy(sampling_rate=0.5)
                )
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
    def test_retry_uses_remaining_deadline(self, mock_monotonic, mock_sleep):
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

    @patch(_RANDOM_TARGET)
    @patch(_SLEEP_TARGET)
    @patch(_MONOTONIC_TARGET)
    def test_raises_before_sleep_exceeds_deadline(
        self, mock_monotonic, mock_sleep, mock_uniform
    ):
        mock_uniform.return_value = 1.0
        mock_monotonic.side_effect = [0, 0, 9.5]
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

    @patch(_SLEEP_TARGET)
    @patch(_MONOTONIC_TARGET)
    def test_deadline_exceeded_raises_early(self, mock_monotonic, mock_sleep):
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
