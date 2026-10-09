# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpClientConnectionInfo:
    """Library-agnostic description of an HTTP client connection."""

    server_address: str
    server_port: int | None = None
    url_scheme: str | None = None
    network_protocol_name: str | None = None
    network_protocol_version: str | None = None
    network_peer_address: str | None = None
    network_peer_port: int | None = None
    network_transport: Literal["tcp", "udp", "pipe", "unix", "quic"] | None = None


class HttpClientConnectionState(enum.Enum):
    """State of an HTTP client connection."""

    IDLE = "idle"
    ACTIVE = "active"


class HttpClientConnection:
    """Telemetry for a single HTTP client connection."""

    def set_state(self, state: HttpClientConnectionState) -> None:
        """Record a change in the connection's state."""

    def end(self, *, end_time: int | None = None) -> None:
        """End the connection. Calling this more than once has no effect."""
