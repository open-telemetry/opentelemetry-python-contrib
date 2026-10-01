# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_PROTOCOL_NAME,
    NETWORK_PROTOCOL_VERSION,
    NETWORK_TRANSPORT,
)

_OMITTED_PROTOCOL_NAMES = frozenset({"http", "https"})


def get_protocol_attributes(name: str | None, version: str | None) -> dict[str, str]:
    """Return ``network.protocol.version`` and, unless it is ``http`` or ``https``, the lowercased ``network.protocol.name``."""
    if not version:
        return {}
    attributes = {NETWORK_PROTOCOL_VERSION: version}
    if name and name.lower() not in _OMITTED_PROTOCOL_NAMES:
        attributes[NETWORK_PROTOCOL_NAME] = name.lower()
    return attributes


def get_peer_attributes(address: str | None, port: int | None) -> dict[str, str | int]:
    """Return ``network.peer.address`` and, when an address is set, ``network.peer.port``."""
    if not address:
        return {}
    attributes: dict[str, str | int] = {NETWORK_PEER_ADDRESS: address}
    if port is not None:
        attributes[NETWORK_PEER_PORT] = port
    return attributes


def get_transport_attributes(transport: str | None) -> dict[str, str]:
    """Return ``network.transport``."""
    if not transport:
        return {}
    return {NETWORK_TRANSPORT: transport}
