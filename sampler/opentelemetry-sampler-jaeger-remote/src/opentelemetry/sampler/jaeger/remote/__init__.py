# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import threading
import weakref
from typing import Literal, Mapping, Sequence

from opentelemetry.context import Context
from opentelemetry.sampler.jaeger.remote._provider import (
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
    SamplingStrategy,
    SamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote._samplers import (
    PerOperationSampler,
    ProbabilisticSampler,
    RateLimitingSampler,
)
from opentelemetry.sdk.trace.sampling import Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

_logger = logging.getLogger(__name__)

_DEFAULT_POLLING_INTERVAL = 60.0  # seconds
_DEFAULT_MAX_OPERATIONS = 256
_DEFAULT_INITIAL_SAMPLING_PROBABILITY = 0.001


def _create_provider(
    protocol: Literal["grpc", "http"],
    endpoint: str,
    headers: Mapping[str, str] | None,
    timeout: float | None,
) -> SamplingStrategyProvider:
    match protocol:
        case "http":
            try:
                # pylint: disable-next=import-outside-toplevel
                from opentelemetry.sampler.jaeger.remote._http_provider import (  # noqa: PLC0415
                    HttpSamplingStrategyProvider,
                )
            except ImportError as error:
                raise ImportError(
                    "protocol='http' requires the 'http' extra: "
                    "pip install opentelemetry-sampler-jaeger-remote[http]"
                ) from error
            return HttpSamplingStrategyProvider(
                endpoint, headers=headers, timeout=timeout
            )
        case "grpc":
            try:
                # pylint: disable-next=import-outside-toplevel
                from opentelemetry.sampler.jaeger.remote._grpc_provider import (  # noqa: PLC0415
                    GrpcSamplingStrategyProvider,
                )
            except ImportError as error:
                raise ImportError(
                    "protocol='grpc' requires the 'grpc' extra: "
                    "pip install opentelemetry-sampler-jaeger-remote[grpc]"
                ) from error
            return GrpcSamplingStrategyProvider(
                endpoint, headers=headers, timeout=timeout
            )
        case _:
            raise ValueError(f"Unsupported protocol: {protocol!r}")


def _build_or_update_sampler(
    current: Sampler,
    strategy: SamplingStrategy,
    max_operations: int,
) -> Sampler:
    match strategy:
        case ProbabilisticStrategy(sampling_rate=sampling_rate):
            if isinstance(current, ProbabilisticSampler):
                current.update(sampling_rate)
                return current
            return ProbabilisticSampler(sampling_rate)
        case RateLimitingStrategy(max_traces_per_second=max_traces_per_second):
            if isinstance(current, RateLimitingSampler):
                current.update(max_traces_per_second)
                return current
            return RateLimitingSampler(max_traces_per_second)
        case PerOperationStrategy(
            default_sampling_probability=default_sampling_probability,
            default_lower_bound_traces_per_second=default_lower_bound_traces_per_second,
            operation_strategies=operation_strategies,
        ):
            per_operation_strategies = tuple(
                (operation.operation, operation.sampling_rate)
                for operation in operation_strategies
            )
            if isinstance(current, PerOperationSampler):
                current.update(
                    default_sampling_probability,
                    default_lower_bound_traces_per_second,
                    per_operation_strategies,
                )
                return current
            return PerOperationSampler(
                default_sampling_probability,
                default_lower_bound_traces_per_second,
                per_operation_strategies,
                max_operations=max_operations,
            )
        case _:
            raise ValueError(f"Unsupported sampling strategy: {strategy!r}")


def _poll_loop(
    sampler_ref: weakref.ReferenceType[JaegerRemoteSampler],
    shutdown_event: threading.Event,
    polling_interval: float,
) -> None:
    while True:
        sampler = sampler_ref()
        if sampler is None:
            return
        # pylint: disable-next=protected-access
        sampler._update_sampler()
        del sampler
        if shutdown_event.wait(polling_interval):
            return


class JaegerRemoteSampler(Sampler):
    """Sampler that polls a Jaeger remote sampling endpoint and delegates
    sampling decisions to whichever strategy specific sampler is currently
    active.

    The endpoint is polled on a background daemon thread, starting
    immediately and then every `polling_interval` seconds.
    """

    def __init__(
        self,
        endpoint: str,
        service_name: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        protocol: Literal["grpc", "http"] = "http",
        initial_sampler: Sampler | None = None,
        polling_interval: float = _DEFAULT_POLLING_INTERVAL,
        max_operations: int = _DEFAULT_MAX_OPERATIONS,
    ) -> None:
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._service_name = service_name
        self._polling_interval = polling_interval
        self._max_operations = max_operations
        self._provider = _create_provider(protocol, endpoint, headers, timeout)
        self._sampler: Sampler = (
            initial_sampler
            if initial_sampler is not None
            else ProbabilisticSampler(_DEFAULT_INITIAL_SAMPLING_PROBABILITY)
        )
        self._thread = threading.Thread(
            target=_poll_loop,
            args=(
                weakref.ref(self),
                self._shutdown_event,
                self._polling_interval,
            ),
            name="JaegerRemoteSamplerWorker",
            daemon=True,
        )
        self._thread.start()

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        with self._lock:
            return self._sampler.should_sample(
                parent_context,
                trace_id,
                name,
                kind=kind,
                attributes=attributes,
                links=links,
                trace_state=trace_state,
            )

    def get_description(self) -> str:
        with self._lock:
            return f"JaegerRemoteSampler{{{self._sampler.get_description()}}}"

    def close(self) -> None:
        """Stop the background polling thread and release the provider."""
        self._shutdown_event.set()
        self._thread.join()
        self._provider.close()

    def __del__(self) -> None:
        if shutdown_event := getattr(self, "_shutdown_event", None):
            shutdown_event.set()
        if provider := getattr(self, "_provider", None):
            provider.close()

    def _update_sampler(self) -> None:
        try:
            strategy = self._provider.get_sampling_strategy(self._service_name)
            with self._lock:
                self._sampler = _build_or_update_sampler(
                    self._sampler, strategy, self._max_operations
                )
        except Exception as error:  # pylint: disable=broad-except
            _logger.error(
                "Failed to update Jaeger sampling strategy for service %r: %s",
                self._service_name,
                error,
            )
