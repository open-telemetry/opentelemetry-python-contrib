# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Internal utilities."""

from __future__ import annotations

from timeit import default_timer

import grpc

from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
)
from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
    RpcSystemNameValues,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_CLIENT_CALL_DURATION,
    RPC_SERVER_CALL_DURATION,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace.status import Status, StatusCode

# error.type value of the calls which did not fail
_NO_ERROR = "None"

# Status codes that are considered errors on the server side, see
# https://opentelemetry.io/docs/specs/semconv/rpc/grpc/#grpc-status
_SERVER_ERROR_CODES = frozenset(
    (
        grpc.StatusCode.UNKNOWN,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.UNIMPLEMENTED,
        grpc.StatusCode.INTERNAL,
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DATA_LOSS,
    )
)


class RpcInfo:
    def __init__(
        self,
        full_method=None,
        metadata=None,
        timeout=None,
        request=None,
        response=None,
        error=None,
    ):
        self.full_method = full_method
        self.metadata = metadata
        self.timeout = timeout
        self.request = request
        self.response = response
        self.error = error


def _server_status(code, details):
    error_status = Status(status_code=StatusCode.ERROR, description=f"{code}:{details}")
    status_codes = {
        grpc.StatusCode.UNKNOWN: error_status,
        grpc.StatusCode.DEADLINE_EXCEEDED: error_status,
        grpc.StatusCode.UNIMPLEMENTED: error_status,
        grpc.StatusCode.INTERNAL: error_status,
        grpc.StatusCode.UNAVAILABLE: error_status,
        grpc.StatusCode.DATA_LOSS: error_status,
    }

    return status_codes.get(code, Status(status_code=StatusCode.UNSET, description=""))


def _create_server_call_duration(meter: Meter) -> Histogram:
    return meter.create_histogram(
        name=RPC_SERVER_CALL_DURATION,
        description="Measures the duration of an incoming Remote Procedure Call (RPC).",
        unit="s",
        explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    )


def _create_client_call_duration(meter: Meter) -> Histogram:
    return meter.create_histogram(
        name=RPC_CLIENT_CALL_DURATION,
        description="Measures the duration of an outgoing Remote Procedure Call (RPC).",
        unit="s",
        explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    )


def _call_duration_attributes(
    full_method: str | bytes | None,
    code: grpc.StatusCode,
    is_error: bool,
) -> dict[str, str]:
    attributes: dict[str, str] = {
        RPC_SYSTEM_NAME: RpcSystemNameValues.GRPC.value,
        RPC_RESPONSE_STATUS_CODE: code.name,
        ERROR_TYPE: code.name if is_error else _NO_ERROR,
    }
    if isinstance(full_method, bytes):
        full_method = full_method.decode()
    if full_method:
        attributes[RPC_METHOD] = full_method.lstrip("/")
    return attributes


def _record_server_call_duration(
    histogram: Histogram | None,
    start: float,
    full_method: str | bytes | None,
    code: grpc.StatusCode | None,
) -> None:
    if histogram is None:
        return
    if code is None:
        code = grpc.StatusCode.UNKNOWN
    attributes = _call_duration_attributes(full_method, code, is_error=code in _SERVER_ERROR_CODES)
    histogram.record(max(default_timer() - start, 0), attributes)


def _record_client_call_duration(
    histogram: Histogram | None,
    start: float,
    full_method: str | bytes | None,
    code: grpc.StatusCode | None,
) -> None:
    if histogram is None:
        return
    if code is None:
        code = grpc.StatusCode.UNKNOWN
    # every status other than OK is an error on the client side
    attributes = _call_duration_attributes(full_method, code, is_error=code != grpc.StatusCode.OK)
    histogram.record(max(default_timer() - start, 0), attributes)
