# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase
from unittest.mock import patch

import grpc

from opentelemetry.sampler.jaeger.remote._grpc_provider import (
    _DEFAULT_TIMEOUT,
    _MAX_RETRIES,
    GrpcSamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
)
from opentelemetry.sampler.jaeger.remote.proto.sampling_pb2 import (  # pylint: disable=no-name-in-module
    OperationSamplingStrategy,
    PerOperationSamplingStrategies,
    ProbabilisticSamplingStrategy,
    RateLimitingSamplingStrategy,
    SamplingStrategyResponse,
    SamplingStrategyType,
)

_ENDPOINT = "localhost:14250"

_SLEEP_TARGET = "opentelemetry.sampler.jaeger.remote._grpc_provider.time.sleep"


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code, details="transient error"):
        super().__init__(details)
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


class TestConstructor(TestCase):
    def test_default_timeout(self):
        provider = GrpcSamplingStrategyProvider(_ENDPOINT)
        self.addCleanup(provider.close)
        self.assertEqual(provider._timeout, _DEFAULT_TIMEOUT)

    def test_explicit_timeout_and_headers(self):
        provider = GrpcSamplingStrategyProvider(
            _ENDPOINT, headers={"Authorization": "Bearer secret"}, timeout=2.5
        )
        self.addCleanup(provider.close)
        self.assertEqual(provider._timeout, 2.5)
        self.assertEqual(
            provider._metadata, (("authorization", "Bearer secret"),)
        )


class TestGetSamplingStrategy(TestCase):
    def setUp(self):
        self.provider = GrpcSamplingStrategyProvider(_ENDPOINT)
        self.addCleanup(self.provider.close)

    def test_probabilistic_strategy(self):
        response = SamplingStrategyResponse(
            strategyType=SamplingStrategyType.PROBABILISTIC,
            probabilisticSampling=ProbabilisticSamplingStrategy(
                samplingRate=0.5
            ),
        )
        with patch.object(
            self.provider._stub, "GetSamplingStrategy", return_value=response
        ):
            strategy = self.provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))

    def test_rate_limiting_strategy(self):
        response = SamplingStrategyResponse(
            strategyType=SamplingStrategyType.RATE_LIMITING,
            rateLimitingSampling=RateLimitingSamplingStrategy(
                maxTracesPerSecond=5
            ),
        )
        with patch.object(
            self.provider._stub, "GetSamplingStrategy", return_value=response
        ):
            strategy = self.provider.get_sampling_strategy("my-service")

        self.assertEqual(
            strategy, RateLimitingStrategy(max_traces_per_second=5)
        )

    def test_per_operation_strategy(self):
        response = SamplingStrategyResponse(
            operationSampling=PerOperationSamplingStrategies(
                defaultSamplingProbability=0.1,
                defaultLowerBoundTracesPerSecond=1.0,
                defaultUpperBoundTracesPerSecond=10.0,
                perOperationStrategies=[
                    OperationSamplingStrategy(
                        operation="op-a",
                        probabilisticSampling=ProbabilisticSamplingStrategy(
                            samplingRate=0.75
                        ),
                    )
                ],
            )
        )
        with patch.object(
            self.provider._stub, "GetSamplingStrategy", return_value=response
        ):
            strategy = self.provider.get_sampling_strategy("my-service")

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
    def test_non_retryable_error_raises_without_sleeping(self, mock_sleep):
        error = _FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT)
        with patch.object(
            self.provider._stub, "GetSamplingStrategy", side_effect=error
        ):
            with self.assertRaises(RuntimeError):
                self.provider.get_sampling_strategy("my-service")

        mock_sleep.assert_not_called()

    @patch(_SLEEP_TARGET)
    def test_retries_transient_error_then_succeeds(self, mock_sleep):
        response = SamplingStrategyResponse(
            probabilisticSampling=ProbabilisticSamplingStrategy(
                samplingRate=0.5
            )
        )
        side_effects = [_FakeRpcError(grpc.StatusCode.UNAVAILABLE), response]
        with patch.object(
            self.provider._stub,
            "GetSamplingStrategy",
            side_effect=side_effects,
        ):
            strategy = self.provider.get_sampling_strategy("my-service")

        self.assertEqual(strategy, ProbabilisticStrategy(sampling_rate=0.5))
        mock_sleep.assert_called_once()

    @patch(_SLEEP_TARGET)
    def test_retries_exhausted_raises(self, mock_sleep):
        errors = [_FakeRpcError(grpc.StatusCode.UNAVAILABLE)] * (
            _MAX_RETRIES + 1
        )
        with patch.object(
            self.provider._stub, "GetSamplingStrategy", side_effect=errors
        ):
            with self.assertRaises(RuntimeError):
                self.provider.get_sampling_strategy("my-service")

        self.assertEqual(mock_sleep.call_count, _MAX_RETRIES)


class TestClose(TestCase):
    # pylint: disable=no-self-use
    def test_close_closes_channel(self):
        provider = GrpcSamplingStrategyProvider(_ENDPOINT)
        with patch.object(provider._channel, "close") as mock_close:
            provider.close()

        mock_close.assert_called_once()
