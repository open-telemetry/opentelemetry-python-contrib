# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""gRPC-specific semantic-convention helpers for the metrics stability migration.

The gRPC RPC semantic conventions changed between v1.37.0 (the "old" experimental
networking conventions) and v1.40.0 (the "new" release-candidate conventions).
Instrumentations opt users in via the ``OTEL_SEMCONV_STABILITY_OPT_IN`` env var:

* default (no opt-in): emit only the v1.37.0 metrics
* ``rpc``: emit only the new metrics
* ``rpc/dup``: emit both

This module only covers the metrics side of the migration.  Span attributes are
still emitted using the pre-migration conventions.
"""

from typing import MutableMapping, Optional

import grpc

from opentelemetry.instrumentation._semconv import (
    _report_new,
    _report_old,
    _StabilityMode,
)
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SERVICE,
    RPC_SYSTEM,
    RPC_SYSTEM_NAME,
    RpcSystemNameValues,
    RpcSystemValues,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_CLIENT_CALL_DURATION,
    RPC_CLIENT_DURATION,
    RPC_SERVER_CALL_DURATION,
    RPC_SERVER_DURATION,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.util.types import AttributeValue

_DEFAULT_RPC_METHOD = "_OTHER"

# Explicit histogram bucket boundaries used for the duration histograms.
_RPC_DURATION_BUCKET_BOUNDARIES_S = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1,
    2.5,
    5,
    7.5,
    10,
)
_RPC_DURATION_BUCKET_BOUNDARIES_MS = tuple(
    b * 1000 for b in _RPC_DURATION_BUCKET_BOUNDARIES_S
)


def _create_client_duration_histograms(meter, sem_conv_opt_in_mode):
    """Create the client-side duration histograms for the active semconv modes."""
    old = new = None
    if _report_old(sem_conv_opt_in_mode):
        old = meter.create_histogram(
            name=RPC_CLIENT_DURATION,
            description="Measures the duration of outbound RPC.",
            unit="ms",
            explicit_bucket_boundaries_advisory=_RPC_DURATION_BUCKET_BOUNDARIES_MS,
        )
    if _report_new(sem_conv_opt_in_mode):
        new = meter.create_histogram(
            name=RPC_CLIENT_CALL_DURATION,
            description="Measures the duration of an outgoing Remote Procedure Call (RPC).",
            unit="s",
            explicit_bucket_boundaries_advisory=_RPC_DURATION_BUCKET_BOUNDARIES_S,
        )
    return old, new


def _create_server_duration_histograms(meter, sem_conv_opt_in_mode):
    """Create the server-side duration histograms for the active semconv modes."""
    old = new = None
    if _report_old(sem_conv_opt_in_mode):
        old = meter.create_histogram(
            name=RPC_SERVER_DURATION,
            description="Measures the duration of inbound RPC.",
            unit="ms",
            explicit_bucket_boundaries_advisory=_RPC_DURATION_BUCKET_BOUNDARIES_MS,
        )
    if _report_new(sem_conv_opt_in_mode):
        new = meter.create_histogram(
            name=RPC_SERVER_CALL_DURATION,
            description="Measures the duration of an incoming Remote Procedure Call (RPC).",
            unit="s",
            explicit_bucket_boundaries_advisory=_RPC_DURATION_BUCKET_BOUNDARIES_S,
        )
    return old, new


def _split_method(full_method: Optional[str]) -> tuple:
    """Return ``(service, method)`` from a raw gRPC path like ``/pkg.Svc/Method``.

    Returns ``(None, None)`` if the path is missing or unparseable.
    """
    if not full_method:
        return None, None
    stripped = full_method.lstrip("/")
    if "/" not in stripped:
        return None, stripped
    service, method = stripped.split("/", 1)
    return service, method


def _build_old_metric_attributes(
    full_method: Optional[str],
    status_code: grpc.StatusCode,
    server_address: Optional[str] = None,
    server_port: Optional[int] = None,
) -> MutableMapping[str, AttributeValue]:
    """Metric attributes for the v1.37.0 duration histograms."""
    service, method = _split_method(full_method)
    attrs: MutableMapping[str, AttributeValue] = {
        RPC_SYSTEM: RpcSystemValues.GRPC.value,
        RPC_GRPC_STATUS_CODE: status_code.value[0],
    }
    if method:
        attrs[RPC_METHOD] = method
    if service:
        attrs[RPC_SERVICE] = service
    if server_address:
        attrs[SERVER_ADDRESS] = server_address
        if server_port is not None:
            attrs[SERVER_PORT] = server_port
    return attrs


def _build_new_metric_attributes(
    full_method: Optional[str],
    status_code: grpc.StatusCode,
    server_address: Optional[str] = None,
    server_port: Optional[int] = None,
) -> MutableMapping[str, AttributeValue]:
    """Metric attributes for the v1.40 ``rpc.{client,server}.call.duration`` histograms."""
    method = full_method.lstrip("/") if full_method else _DEFAULT_RPC_METHOD
    attrs: MutableMapping[str, AttributeValue] = {
        RPC_SYSTEM_NAME: RpcSystemNameValues.GRPC.value,
        RPC_METHOD: method,
        RPC_RESPONSE_STATUS_CODE: status_code.name,
    }
    if server_address:
        attrs[SERVER_ADDRESS] = server_address
        if server_port is not None:
            attrs[SERVER_PORT] = server_port
    if status_code != grpc.StatusCode.OK:
        attrs[ERROR_TYPE] = status_code.name
    return attrs


def _record_client_duration(
    old_histogram,
    new_histogram,
    elapsed_seconds: float,
    full_method: Optional[str],
    status_code: grpc.StatusCode,
    server_address: Optional[str],
    server_port: Optional[int],
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Record client-side duration on the histograms enabled by ``sem_conv_opt_in_mode``."""
    if old_histogram is not None and _report_old(sem_conv_opt_in_mode):
        old_histogram.record(
            elapsed_seconds * 1000,
            attributes=_build_old_metric_attributes(
                full_method, status_code, server_address, server_port
            ),
        )
    if new_histogram is not None and _report_new(sem_conv_opt_in_mode):
        new_histogram.record(
            elapsed_seconds,
            attributes=_build_new_metric_attributes(
                full_method, status_code, server_address, server_port
            ),
        )


def _record_server_duration(
    old_histogram,
    new_histogram,
    elapsed_seconds: float,
    full_method: Optional[str],
    status_code: grpc.StatusCode,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Record server-side duration on the histograms enabled by ``sem_conv_opt_in_mode``."""
    if old_histogram is not None and _report_old(sem_conv_opt_in_mode):
        old_histogram.record(
            elapsed_seconds * 1000,
            attributes=_build_old_metric_attributes(full_method, status_code),
        )
    if new_histogram is not None and _report_new(sem_conv_opt_in_mode):
        new_histogram.record(
            elapsed_seconds,
            attributes=_build_new_metric_attributes(full_method, status_code),
        )
