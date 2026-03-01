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
from opentelemetry.semconv.attributes.error_attributes import (
    ERROR_TYPE,
    ErrorTypeValues,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
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
    code: Optional[grpc.StatusCode],
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
    if code is None:
        code = grpc.StatusCode.OK
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
            span.set_attribute(ERROR_TYPE, code.name if code else  ErrorTypeValues.OTHER)
        status_description = f"{code}:{description}" if description else str(code)
        span.set_status(Status(StatusCode.ERROR, description=status_description))


def _add_error_details_to_span(span, exc, span_kind, sem_conv_opt_in_mode):
    """Record exception details on a span.

    Sets the span status to ERROR with a description, sets error.type
    (new semconv only), and records the exception (old semconv only).

    For grpc.RpcError, delegates to _apply_grpc_status which handles
    the gRPC status code attributes.  For all other exceptions, sets
    error.type to the fully-qualified exception class name.
    """
    if _report_new(sem_conv_opt_in_mode):
        description = str(exc)
    else:
        description = f"{type(exc).__name__}: {exc}"

    if isinstance(exc, grpc.RpcError):
        _apply_grpc_status(span, exc.code(), span_kind, sem_conv_opt_in_mode, description)
    else:
        span.set_status(Status(StatusCode.ERROR, description=description))
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(ERROR_TYPE, type(exc).__qualname__)

    if _report_old(sem_conv_opt_in_mode):
        span.record_exception(exc)


def _apply_server_error(span, exc, code, details, sem_conv_opt_in_mode):
    """Handle span status for a server-side exception.

    If a gRPC status code was explicitly set (via abort/set_code), apply it.
    Otherwise record the unexpected exception details.
    """
    if code is not None:
        _apply_grpc_status(span, code, trace.SpanKind.SERVER, sem_conv_opt_in_mode, details)
    else:
        _add_error_details_to_span(span, exc, trace.SpanKind.SERVER, sem_conv_opt_in_mode)


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


def _parse_grpc_target(target: str) -> tuple:
    """Parse a gRPC target string into a ``(server.address, server.port)`` 2-tuple.

    Follows the OTel RPC semantic convention for ``server.address``/
    ``server.port`` on client spans:

    * ``"host:port"`` / ``"[ipv6]:port"`` — bare DNS address, parse normally
    * ``"dns://[resolver]/host:port"`` — DNS URI, skip resolver, parse endpoint
    * ``"unix:path"`` / ``"unix:///path"`` — socket path becomes
      ``server.address``, no port
    * ``"ipv4:..."`` / ``"ipv6:..."`` — ``scheme:addr`` format (no ``//``),
      may list multiple addresses; whole target becomes ``server.address``, no port
    * ``"scheme://..."`` with an unknown scheme (e.g. ``"zk://..."``) — whole
      target becomes ``server.address``, no port

    Returns ``(address, port)`` where *port* is an :class:`int` or ``None``.
    """
    if not target:
        return None, None

    # Unix domain sockets: server.address = the socket path, no port.
    # Handles both "unix:path" and "unix:///path" (URI form).
    if target.startswith("unix:") or target.startswith("unix-abstract:"):
        prefix = "unix:" if target.startswith("unix:") else "unix-abstract:"
        path = target[len(prefix):]
        # Strip the authority component from URI form ("//[authority]/path")
        if path.startswith("//"):
            slash = path.find("/", 2)   # first "/" after the leading "//"
            path = path[slash:] if slash != -1 else ""
        return path or None, None

    # ipv4/ipv6 scheme can list multiple addresses; no single low-cardinality
    # identifier can be derived → return the whole target string, no port.
    if target.startswith("ipv4:") or target.startswith("ipv6:"):
        return target, None

    # URI form: scheme://[authority]/endpoint
    if "://" in target:
        scheme, _, rest = target.partition("://")
        if scheme == "dns":
            # dns://[resolver]/host:port — endpoint follows the authority
            slash = rest.find("/")
            endpoint = rest[slash + 1:] if slash != -1 else rest
            return _parse_host_port(endpoint)
        # Unknown URI scheme — cannot determine a low-cardinality identifier.
        return target, None

    # Plain "host:port" (implicit DNS)
    return _parse_host_port(target)


def _parse_host_port(target: str) -> tuple:
    """Parse a bare ``"host:port"`` or ``"[ipv6]:port"`` string."""
    if not target:
        return None, None

    # IPv6 literal: "[::1]:50051"
    if target.startswith("["):
        bracket_end = target.find("]")
        if bracket_end == -1:
            return None, None
        host = target[1:bracket_end]
        remainder = target[bracket_end + 1:]
        if remainder.startswith(":"):
            try:
                return host, int(remainder[1:])
            except ValueError:
                pass
        return host, None

    # Plain "host:port" or bare "host"
    if ":" in target:
        host, _, port_str = target.rpartition(":")
        try:
            return host, int(port_str)
        except ValueError:
            pass

    return target, None


def _set_server_address_port(
    result: MutableMapping[str, AttributeValue],
    host: Optional[str],
    port: Optional[int],
    sem_conv_opt_in_mode: _StabilityMode,
) -> None:
    """Set server address/port attributes on a gRPC client span.

    New only: server.address + server.port
    (The old implementation does not set these.)
    """
    if not _report_new(sem_conv_opt_in_mode):
        return
    if host:
        result[SERVER_ADDRESS] = host
    if port is not None:
        result[SERVER_PORT] = port
