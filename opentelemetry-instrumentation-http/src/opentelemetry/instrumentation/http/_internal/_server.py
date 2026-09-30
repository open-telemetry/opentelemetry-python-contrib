# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from urllib.parse import SplitResult

from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


def get_server_attributes(
    parts: SplitResult | None, server_address: str | None, server_port: int | None
) -> dict[str, str | int]:
    """Return ``server.address`` and ``server.port``.

    An explicit ``server_address`` is recorded with ``server_port``. Otherwise
    both come from the URL, and ``server_port`` is ignored. A missing port
    defaults to the port of the URL scheme. An invalid URL port is omitted.
    """
    scheme = parts.scheme if parts is not None else ""
    if server_address:
        address, port = server_address, server_port
    elif parts is not None and parts.hostname:
        address = parts.hostname
        try:
            port = parts.port
        except ValueError:
            return {SERVER_ADDRESS: address}
    else:
        return {}
    if port is None:
        port = _DEFAULT_PORTS.get(scheme)
    attributes: dict[str, str | int] = {SERVER_ADDRESS: address}
    if port is not None:
        attributes[SERVER_PORT] = port
    return attributes
