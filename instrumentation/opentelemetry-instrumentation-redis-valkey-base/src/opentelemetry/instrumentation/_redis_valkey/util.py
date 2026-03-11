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
#
"""
Shared utility functions for Redis/Valkey instrumentation.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
    NET_TRANSPORT,
)
from opentelemetry.semconv.trace import NetTransportValues
from opentelemetry.trace import Span

_FIELD_TYPES = ["NUMERIC", "TEXT", "GEO", "TAG", "VECTOR"]


def _extract_conn_attributes(
    conn_kwargs: dict[str, Any],
    db_system: str,
    db_system_attr: str,
    db_index_attr: str,
) -> dict[str, Any]:
    """Transform connection info into a dict of span attributes.

    Args:
        conn_kwargs: Connection keyword arguments from the client's connection pool.
        db_system: The database system name (e.g., "redis" or "valkey").
        db_system_attr: The attribute key for DB_SYSTEM.
        db_index_attr: The attribute key for the database index.
    """
    attributes: dict[str, Any] = {
        db_system_attr: db_system,
    }
    db = conn_kwargs.get("db", 0)
    attributes[db_index_attr] = db
    if "path" in conn_kwargs:
        attributes[NET_PEER_NAME] = conn_kwargs.get("path", "")
        attributes[NET_TRANSPORT] = NetTransportValues.OTHER.value
    else:
        attributes[NET_PEER_NAME] = conn_kwargs.get("host", "localhost")
        attributes[NET_PEER_PORT] = conn_kwargs.get("port", 6379)
        attributes[NET_TRANSPORT] = NetTransportValues.IP_TCP.value

    return attributes


def _format_command_args(args: list[str]) -> str:
    """Format and sanitize command arguments, and trim them as needed."""
    cmd_max_len = 1000
    value_too_long_mark = "..."

    # Sanitized query format: "COMMAND ? ?"
    args_length = len(args)
    if args_length > 0:
        out = [str(args[0])] + ["?"] * (args_length - 1)
        out_str = " ".join(out)

        if len(out_str) > cmd_max_len:
            out_str = (
                out_str[: cmd_max_len - len(value_too_long_mark)]
                + value_too_long_mark
            )
    else:
        out_str = ""

    return out_str


def _set_span_attribute_if_value(
    span: Span, name: str, value: Any
) -> None:
    if value is not None and value != "":
        span.set_attribute(name, value)


def _value_or_none(values: Any, n: int) -> Any:
    try:
        return values[n]
    except IndexError:
        return None


def _set_connection_attributes(
    span: Span,
    conn: Any,
    db_system: str,
    db_system_attr: str,
    db_index_attr: str,
) -> None:
    """Set connection attributes on a span from a client instance."""
    if not span.is_recording() or not hasattr(conn, "connection_pool"):
        return
    for key, value in _extract_conn_attributes(
        conn.connection_pool.connection_kwargs,
        db_system,
        db_system_attr,
        db_index_attr,
    ).items():
        span.set_attribute(key, value)


def _build_span_name(
    instance: Any,
    cmd_args: tuple[Any, ...],
    backend_name: str,
) -> str:
    """Build a span name from the command arguments.

    Args:
        instance: The client instance.
        cmd_args: The command arguments.
        backend_name: The backend name (e.g., "redis" or "valkey").
    """
    if len(cmd_args) > 0 and cmd_args[0]:
        if cmd_args[0] == "FT.SEARCH":
            name = f"{backend_name}.search"
        elif cmd_args[0] == "FT.CREATE":
            name = f"{backend_name}.create_index"
        else:
            name = cmd_args[0]
    else:
        name = instance.connection_pool.connection_kwargs.get("db", 0)
    return name


def _add_create_attributes(
    span: Span,
    args: tuple[Any, ...],
    backend_name: str,
) -> None:
    """Add FT.CREATE index attributes to a span."""
    _set_span_attribute_if_value(
        span, f"{backend_name}.create_index.index", _value_or_none(args, 1)
    )
    try:
        schema_index = args.index("SCHEMA")
    except ValueError:
        return
    schema = args[schema_index:]
    field_attribute = "".join(
        f"Field(name: {schema[index - 1]}, type: {schema[index]});"
        for index in range(1, len(schema))
        if schema[index] in _FIELD_TYPES
    )
    _set_span_attribute_if_value(
        span,
        f"{backend_name}.create_index.fields",
        field_attribute,
    )


def _add_search_attributes(
    span: Span,
    response: Any,
    args: tuple[Any, ...],
    backend_name: str,
) -> None:
    """Add FT.SEARCH response attributes to a span."""
    _set_span_attribute_if_value(
        span, f"{backend_name}.search.index", _value_or_none(args, 1)
    )
    _set_span_attribute_if_value(
        span, f"{backend_name}.search.query", _value_or_none(args, 2)
    )
    number_of_returned_documents = _value_or_none(response, 0)
    _set_span_attribute_if_value(
        span, f"{backend_name}.search.total", number_of_returned_documents
    )
    if "NOCONTENT" in args or not number_of_returned_documents:
        return
    for document_number in range(number_of_returned_documents):
        document_index = _value_or_none(response, 1 + 2 * document_number)
        if document_index:
            document = response[2 + 2 * document_number]
            for attribute_name_index in range(0, len(document), 2):
                _set_span_attribute_if_value(
                    span,
                    f"{backend_name}.search.xdoc_{document_index}.{document[attribute_name_index]}",
                    document[attribute_name_index + 1],
                )


def _build_span_meta_data_for_pipeline(
    instance: Any,
    backend_name: str,
) -> tuple[list[Any], str, str]:
    """Build span metadata for a pipeline execution.

    Returns:
        A tuple of (command_stack, resource, span_name).
    """
    try:
        command_stack = (
            instance.command_stack
            if hasattr(instance, "command_stack")
            else instance._command_stack
        )

        cmds = [
            _format_command_args(c.args if hasattr(c, "args") else c[0])
            for c in command_stack
        ]
        resource = "\n".join(cmds)

        span_name = " ".join(
            [
                (c.args[0] if hasattr(c, "args") else c[0][0])
                for c in command_stack
            ]
        )
    except (AttributeError, IndexError):
        command_stack = []
        resource = ""
        span_name = ""

    return command_stack, resource, span_name or backend_name
