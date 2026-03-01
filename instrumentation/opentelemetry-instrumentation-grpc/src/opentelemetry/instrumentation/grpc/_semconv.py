# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""gRPC-specific semantic convention helpers for the stability migration."""

from typing import MutableMapping, Optional

import grpc

from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.instrumentation._semconv import (
    _StabilityMode,
    _report_new,
    _report_old,
    set_int_attribute,
    set_string_attribute,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_IP,
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_SERVICE,
    RPC_SYSTEM,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
)
from opentelemetry.util.types import AttributeValue

# New stable RPC attribute names. Not yet published as stable constants in the
# opentelemetry-semantic-conventions package because the stable RPC conventions
# are still a work in progress.
RPC_SYSTEM_NAME = "rpc.system.name"
RPC_RESPONSE_STATUS_CODE = "rpc.response.status_code"

# gRPC status codes that are considered errors on the server side under the
# new stable RPC conventions. See:
# https://github.com/open-telemetry/semantic-conventions/blob/main/docs/rpc/rpc-spans.md
_GRPC_SERVER_ERROR_STATUS_CODES = frozenset({
    grpc.StatusCode.UNKNOWN,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.UNIMPLEMENTED,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DATA_LOSS,
})


def _apply_grpc_status(
    span,
    code: grpc.StatusCode,
    span_kind: trace.SpanKind,
    sem_conv_opt_in_mode: _StabilityMode,
    description: Optional[str] = None,
) -> None:
    """Set gRPC status code attributes and update the span status.

    Handles both old and new semantic convention modes.  Error criterion:

    * Client (SpanKind.CLIENT): any non-OK code is an error.
    * Server (SpanKind.SERVER): only the subset defined in
      _GRPC_SERVER_ERROR_STATUS_CODES.
    """
    if _report_old(sem_conv_opt_in_mode):
        span.set_attribute(RPC_GRPC_STATUS_CODE, code.value[0])
    if _report_new(sem_conv_opt_in_mode):
        span.set_attribute(RPC_RESPONSE_STATUS_CODE, code.name)

    is_error = (
        code in _GRPC_SERVER_ERROR_STATUS_CODES
        if span_kind == trace.SpanKind.SERVER
        else code != grpc.StatusCode.OK
    )

    if is_error:
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(ERROR_TYPE, code.name)
        span.set_status(Status(StatusCode.ERROR, description=description))


def _set_rpc_system(
    result: MutableMapping[str, AttributeValue],
    system: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set rpc.system (old) or rpc.system.name (new)."""
    if _report_old(sem_conv_opt_in_mode):
        result[RPC_SYSTEM] = system
    if _report_new(sem_conv_opt_in_mode):
        result[RPC_SYSTEM_NAME] = system


def _set_rpc_method(
    result: MutableMapping[str, AttributeValue],
    full_method: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set rpc.method (and rpc.service in old mode) from a full method path.

    ``full_method`` is the raw gRPC path, e.g. ``/helloworld.Greeter/SayHello``
    (leading slash is stripped automatically).

    Old: rpc.method = bare method name, rpc.service = package-qualified service
    New: rpc.method = fully-qualified "Service/Method" (no rpc.service)
    """
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, RPC_METHOD, full_method)
    if _report_old(sem_conv_opt_in_mode):
        stripped = full_method.lstrip("/")
        if "/" in stripped:
            service, method = stripped.split("/", 1)
            set_string_attribute(result, RPC_METHOD, method)
            set_string_attribute(result, RPC_SERVICE, service)
        else:
            set_string_attribute(result, RPC_METHOD, stripped)


def _set_rpc_grpc_status_code(
    result: MutableMapping[str, AttributeValue],
    code_int: int,
    code_str: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set gRPC status code attribute.

    Old: rpc.grpc.status_code (integer, e.g. 0 for OK)
    New: rpc.response.status_code (string, e.g. "OK"); non-OK also sets error.type
    """
    if _report_old(sem_conv_opt_in_mode):
        result[RPC_GRPC_STATUS_CODE] = code_int
    if _report_new(sem_conv_opt_in_mode):
        result[RPC_RESPONSE_STATUS_CODE] = code_str
        if code_int != 0:  # non-OK status
            result[ERROR_TYPE] = code_str


def _set_rpc_peer_ip_server(
    result: MutableMapping[str, AttributeValue],
    ip: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set the client's IP address on a gRPC server span.

    Old: net.peer.ip
    New: network.peer.address
    """
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, NET_PEER_IP, ip)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, NETWORK_PEER_ADDRESS, ip)


def _set_rpc_peer_port_server(
    result: MutableMapping[str, AttributeValue],
    port: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set the client's port on a gRPC server span.

    Old: net.peer.port (string)
    New: network.peer.port (int)
    """
    if _report_old(sem_conv_opt_in_mode):
        result[NET_PEER_PORT] = port
    if _report_new(sem_conv_opt_in_mode):
        set_int_attribute(result, NETWORK_PEER_PORT, port)


def _set_rpc_peer_name_server(
    result: MutableMapping[str, AttributeValue],
    name: str,
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set the client's hostname on a gRPC server span.

    Old: net.peer.name
    New: network.peer.address (only if not already set by _set_rpc_peer_ip_server)
    """
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, NET_PEER_NAME, name)
    if _report_new(sem_conv_opt_in_mode):
        if not result.get(NETWORK_PEER_ADDRESS):
            set_string_attribute(result, NETWORK_PEER_ADDRESS, name)
