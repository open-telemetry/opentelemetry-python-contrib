# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Internal utilities."""

import grpc

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
    error_status = Status(
        status_code=StatusCode.ERROR, description=f"{code}:{details}"
    )
    status_codes = {
        grpc.StatusCode.UNKNOWN: error_status,
        grpc.StatusCode.DEADLINE_EXCEEDED: error_status,
        grpc.StatusCode.UNIMPLEMENTED: error_status,
        grpc.StatusCode.INTERNAL: error_status,
        grpc.StatusCode.UNAVAILABLE: error_status,
        grpc.StatusCode.DATA_LOSS: error_status,
    }

    return status_codes.get(
        code, Status(status_code=StatusCode.UNSET, description="")
    )
