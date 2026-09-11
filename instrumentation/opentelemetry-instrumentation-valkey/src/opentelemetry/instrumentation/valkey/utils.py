# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pyright: reportUnusedFunction=false

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from valkey.exceptions import ResponseError

from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_OPERATION_BATCH_SIZE,
    DB_OPERATION_NAME,
    DB_QUERY_TEXT,
    DB_RESPONSE_STATUS_CODE,
    DB_STORED_PROCEDURE_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_TRANSPORT,
    NetworkTransportValues,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.metrics.db_metrics import DB_CLIENT_OPERATION_DURATION

if TYPE_CHECKING:
    from opentelemetry.instrumentation.valkey.types import (
        AsyncPipelineInstance,
        AsyncValkeyInstance,
        CommandStackEntry,
        PipelineInstance,
        ValkeyInstance,
    )
    from opentelemetry.metrics import Histogram, Meter
    from opentelemetry.util.types import AttributeValue

# ``db.system.name`` has no generated enum member for Valkey: it is absent from
# the semantic conventions registry, both in the stable and in the incubating
# module. Track https://github.com/open-telemetry/semantic-conventions and swap
# this literal for ``DbSystemNameValues.VALKEY`` once the value is registered.
DB_SYSTEM_NAME_VALKEY = "valkey"

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 6379
_DEFAULT_NAMESPACE = "0"

_CMD_MAX_LEN = 1000
_VALUE_TOO_LONG_MARK = "..."

# https://opentelemetry.io/docs/specs/semconv/database/database-metrics/
_DB_DURATION_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.05,
    0.1,
    0.5,
    1,
    5,
    10,
]

# https://opentelemetry.io/docs/specs/semconv/db/redis/ requires pipelined and
# transactional calls to be named MULTI or PIPELINE rather than the generic
# BATCH term used by the database conventions.
_MULTI_OPERATION_NAME = "MULTI"
_PIPELINE_OPERATION_NAME = "PIPELINE"

# Commands whose first argument names a Lua script or a function. EVAL and
# EVAL_RO are excluded on purpose: their first argument is the script body, not
# a name or a sha1 digest.
_STORED_PROCEDURE_COMMANDS = ("EVALSHA", "EVALSHA_RO", "FCALL", "FCALL_RO")


# Attributes valkey-py uses for the "this pipeline is a transaction" flag. The
# name differs between the sync client, the async client and .multi().
_TRANSACTION_FLAGS = ("transaction", "is_transaction", "explicit_transaction")

# Valkey server error replies start with an upper case error code, e.g.
# "WRONGTYPE Operation against a key holding the wrong kind of value".
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _format_command_args(args: tuple[Any, ...] | list[Any]) -> str:
    """Format and sanitize command arguments, and trim them as needed."""
    if not args:
        return ""
    # Sanitized query format: "COMMAND ? ?"
    out_str = str(args[0]) + " ?" * (len(args) - 1)
    if len(out_str) > _CMD_MAX_LEN:
        out_str = out_str[: _CMD_MAX_LEN - len(_VALUE_TOO_LONG_MARK)] + _VALUE_TOO_LONG_MARK
    return out_str


def _get_connection_attributes(
    instance: ValkeyInstance | AsyncValkeyInstance,
) -> dict[str, AttributeValue]:
    """Return the connection-derived span/metric attributes for a Valkey client.

    Cluster clients hold a node manager rather than a single connection pool,
    and clients built in tests may have a mocked pool, so this returns an
    empty dict when the attributes are unavailable.
    """
    connection_pool = getattr(instance, "connection_pool", None)
    connection_kwargs = getattr(connection_pool, "connection_kwargs", None)
    if not isinstance(connection_kwargs, dict):
        return {}
    connection_kwargs = cast("dict[str, Any]", connection_kwargs)

    attributes: dict[str, AttributeValue] = {}

    db = connection_kwargs.get("db")
    # Written directly rather than through a helper because the default index 0
    # is falsy and must still be reported.
    attributes[DB_NAMESPACE] = _DEFAULT_NAMESPACE if db is None else str(db)

    # A non-cluster client talks to exactly one node, so the peer is always the
    # configured server, there is no separate node to resolve per operation.
    if "path" in connection_kwargs:
        path = connection_kwargs.get("path", "")
        attributes[SERVER_ADDRESS] = path
        attributes[NETWORK_PEER_ADDRESS] = path
        attributes[NETWORK_TRANSPORT] = NetworkTransportValues.UNIX.value
    else:
        host = connection_kwargs.get("host", _DEFAULT_HOST)
        port = int(connection_kwargs.get("port", _DEFAULT_PORT))
        attributes[SERVER_ADDRESS] = host
        attributes[SERVER_PORT] = port
        attributes[NETWORK_PEER_ADDRESS] = host
        attributes[NETWORK_PEER_PORT] = port
        attributes[NETWORK_TRANSPORT] = NetworkTransportValues.TCP.value

    return attributes


def _get_common_attributes(
    instance: Any,
    operation_name: str,
    query_text: str | None,
    stored_procedure_name: str | None,
    operation_batch_size: int | None,
) -> dict[str, AttributeValue]:
    """Return the attributes reported on both the span and the duration metric."""
    attributes: dict[str, AttributeValue] = {DB_SYSTEM_NAME: DB_SYSTEM_NAME_VALKEY}
    if operation_name:
        attributes[DB_OPERATION_NAME] = operation_name
    attributes.update(_get_connection_attributes(instance))
    if query_text is not None:
        attributes[DB_QUERY_TEXT] = query_text
    if stored_procedure_name is not None:
        attributes[DB_STORED_PROCEDURE_NAME] = stored_procedure_name
    if operation_batch_size is not None:
        attributes[DB_OPERATION_BATCH_SIZE] = operation_batch_size
    return attributes


def _get_span_name(operation_name: str) -> str:
    """Build the span name from ``db.operation.name``.

    The Redis conventions exclude ``db.namespace`` from the span name because a
    numeric database index reads confusingly, which leaves the operation name as
    the whole name.
    """
    return operation_name or DB_SYSTEM_NAME_VALKEY


def _get_operation_name(args: tuple[Any, ...]) -> str:
    """Return ``db.operation.name`` for a single command."""
    if args and args[0]:
        return str(args[0])
    return ""


def _get_command_stack(
    instance: PipelineInstance | AsyncPipelineInstance,
) -> list[tuple[Any, ...]]:
    """Return the arguments of every command queued on a pipeline.

    ``Pipeline`` queues ``(args, options)`` tuples while ``ClusterPipeline``
    queues ``PipelineCommand`` objects, and the async cluster pipeline keeps
    them on a private attribute.
    """
    command_stack: list[CommandStackEntry] | None = getattr(instance, "command_stack", None)
    if not isinstance(command_stack, list):
        command_stack = getattr(instance, "_command_stack", None)
    if not isinstance(command_stack, list):
        return []

    commands: list[tuple[Any, ...]] = []
    for entry in command_stack:
        if isinstance(entry, tuple):
            commands.append(tuple(entry[0]))
            continue
        args = getattr(entry, "args", None)
        if isinstance(args, tuple):
            commands.append(cast("tuple[Any, ...]", args))
    return commands


def _get_stored_procedure_name(args: tuple[Any, ...]) -> str | None:
    """Return ``db.stored_procedure.name`` for a Lua script or function call."""
    if len(args) < 2 or not args[0]:
        return None
    if str(args[0]).upper() not in _STORED_PROCEDURE_COMMANDS:
        return None
    return str(args[1])


def _is_transaction(instance: PipelineInstance | AsyncPipelineInstance) -> bool:
    """Return whether a pipeline is executed as a MULTI/EXEC transaction."""
    for flag in _TRANSACTION_FLAGS:
        value = getattr(instance, flag, False)
        # Valkey.transaction is also the name of a method, which the async
        # pipeline does not shadow with a flag, so only accept a real boolean.
        if isinstance(value, bool) and value:
            return True
    return False


def _get_shared_command(command_stack: list[tuple[Any, ...]]) -> str | None:
    """Return the command shared by every queued operation, if there is one."""
    if not command_stack:
        return None
    first = _get_operation_name(command_stack[0])
    if not first:
        return None
    if any(_get_operation_name(command) != first for command in command_stack):
        return None
    return first


def _get_batch_operation_name(
    instance: PipelineInstance | AsyncPipelineInstance,
    command_stack: list[tuple[Any, ...]],
) -> str:
    """Return ``db.operation.name`` for a pipeline or transaction.

    The Redis conventions ask for ``MULTI`` or ``PIPELINE``, with the command
    prepended to it when every queued operation shares the same one.
    """
    name = _MULTI_OPERATION_NAME if _is_transaction(instance) else _PIPELINE_OPERATION_NAME
    shared_command = _get_shared_command(command_stack)
    if shared_command is None:
        return name
    return f"{name} {shared_command}"


def _get_batch_stored_procedure_name(
    command_stack: list[tuple[Any, ...]],
) -> str | None:
    """Return the stored procedure shared by every queued operation, if any."""
    if not command_stack:
        return None
    first = _get_stored_procedure_name(command_stack[0])
    if any(_get_stored_procedure_name(command) != first for command in command_stack):
        return None
    return first


def _get_batch_query_text(command_stack: list[tuple[Any, ...]]) -> str:
    """Return ``db.query.text`` for a pipeline or transaction.

    Commands are joined with a newline, the separator the Redis CLI uses, and
    collapse to a single entry when every queued operation has the same text.
    """
    queries = [_format_command_args(command) for command in command_stack]
    if len(set(queries)) == 1:
        return queries[0]
    return "\n".join(queries)


def _get_error_status_code(exception: BaseException) -> str | None:
    """Return ``db.response.status_code``, i.e. the Valkey server error code."""
    if not isinstance(exception, ResponseError):
        return None
    message = str(exception).split(maxsplit=1)
    if message and _ERROR_CODE_PATTERN.match(message[0]):
        return message[0]
    return None


def _get_error_attributes(error_type: str, status_code: str | None) -> dict[str, AttributeValue]:
    """Return the error attributes shared by the span and the duration metric."""
    attributes: dict[str, AttributeValue] = {ERROR_TYPE: error_type}
    if status_code is not None:
        attributes[DB_RESPONSE_STATUS_CODE] = status_code
    return attributes


def _create_duration_histogram(meter: Meter) -> Histogram:
    """Create the ``db.client.operation.duration`` histogram."""
    return meter.create_histogram(
        name=DB_CLIENT_OPERATION_DURATION,
        description="Duration of database client operations.",
        unit="s",
        explicit_bucket_boundaries_advisory=_DB_DURATION_BUCKETS,
    )
