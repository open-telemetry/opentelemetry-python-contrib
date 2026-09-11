# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Types used by the Valkey instrumentation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import valkey.asyncio.client
import valkey.asyncio.cluster
import valkey.client
import valkey.cluster
import valkey.connection

from opentelemetry.trace import Span

RequestHook = Callable[[Span, valkey.connection.Connection, list[Any], dict[str, Any]], None]
ResponseHook = Callable[[Span, valkey.connection.Connection, Any], None]


class QueuedCommand(Protocol):
    """A command queued on a ``ClusterPipeline``, exposing just what we read."""

    args: tuple[Any, ...]


CommandStackEntry = tuple[tuple[Any, ...], dict[str, Any]] | QueuedCommand

AsyncPipelineInstance = TypeVar(
    "AsyncPipelineInstance",
    valkey.asyncio.client.Pipeline,
    valkey.asyncio.cluster.ClusterPipeline,
)
AsyncValkeyInstance = TypeVar(
    "AsyncValkeyInstance",
    valkey.asyncio.Valkey,
    valkey.asyncio.ValkeyCluster,
)
PipelineInstance = TypeVar(
    "PipelineInstance",
    valkey.client.Pipeline,
    valkey.cluster.ClusterPipeline,
)
ValkeyInstance = TypeVar("ValkeyInstance", valkey.client.Valkey, valkey.cluster.ValkeyCluster)
