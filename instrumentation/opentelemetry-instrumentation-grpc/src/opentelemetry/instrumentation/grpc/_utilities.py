# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Internal utilities."""

import grpc

from opentelemetry.instrumentation._semconv import _set_error_type
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace.status import Status, StatusCode


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


def _set_grpc_error_type(span, error=None, status_code=None):
    """Record ``error.type`` for a failed gRPC call.

    The RPC semantic conventions ask for the gRPC status code when the call returned one,
    and for the canonical class name of the exception otherwise.
    """
    if status_code is None and isinstance(error, grpc.RpcError):
        status_code = error.code()
    if status_code is not None:
        span.set_attribute(ERROR_TYPE, status_code.name)
        return
    _set_error_type(error, span)


def _set_server_status(span, code, details):
    """Set the span status for a gRPC server call, recording ``error.type`` when it failed."""
    status = _server_status(code, details)
    if status.status_code is StatusCode.ERROR:
        span.set_attribute(ERROR_TYPE, code.name)
    span.set_status(status)
