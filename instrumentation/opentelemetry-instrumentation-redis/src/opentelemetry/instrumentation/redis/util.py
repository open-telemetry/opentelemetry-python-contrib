# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
#
"""
Some utils used by the redis integration
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation._semconv import (
    _set_db_redis_database_index,
    _set_db_system,
    _set_http_net_peer_name_client,
    _set_http_peer_port_client,
    _set_net_transport,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NetworkTransportValues,
)
from opentelemetry.semconv.trace import (
    DbSystemValues,
    NetTransportValues,
)
from opentelemetry.trace import Span

if TYPE_CHECKING:
    from opentelemetry.instrumentation.redis.custom_types import (
        AsyncPipelineInstance,
        AsyncRedisInstance,
        PipelineInstance,
        RedisInstance,
    )

_FIELD_TYPES = ["NUMERIC", "TEXT", "GEO", "TAG", "VECTOR"]


def _extract_conn_attributes(
    conn_kwargs, db_sem_conv_opt_in_mode, http_sem_conv_opt_in_mode
):
    """Transform redis conn info into dict"""
    attributes = {}
    _set_db_system(
        attributes, DbSystemValues.REDIS.value, db_sem_conv_opt_in_mode
    )

    db = conn_kwargs.get("db", 0)
    _set_db_redis_database_index(attributes, db, db_sem_conv_opt_in_mode)
    if "path" in conn_kwargs:
        _set_http_net_peer_name_client(
            attributes, conn_kwargs.get("path", ""), http_sem_conv_opt_in_mode
        )
        _set_net_transport(
            attributes,
            NetTransportValues.OTHER.value,
            NetworkTransportValues.UNIX.value,
            http_sem_conv_opt_in_mode,
        )
    else:
        _set_http_net_peer_name_client(
            attributes,
            conn_kwargs.get("host", "localhost"),
            http_sem_conv_opt_in_mode,
        )
        _set_http_peer_port_client(
            attributes,
            conn_kwargs.get("port", 6379),
            http_sem_conv_opt_in_mode,
        )
        _set_net_transport(
            attributes,
            NetTransportValues.IP_TCP.value,
            NetworkTransportValues.TCP.value,
            http_sem_conv_opt_in_mode,
        )

    return attributes


def _format_command_args(args: list[str]):
    """Format and sanitize command arguments, and trim them as needed"""
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


def _set_span_attribute_if_value(span, name, value):
    if value is not None and value != "":
        span.set_attribute(name, value)


def _value_or_none(values, n):
    try:
        return values[n]
    except IndexError:
        return None


def _set_connection_attributes(
    span: Span,
    conn: RedisInstance | AsyncRedisInstance,
    db_sem_conv_opt_in_mode,
    http_sem_conv_opt_in_mode,
) -> None:
    if not span.is_recording() or not hasattr(conn, "connection_pool"):
        return
    for key, value in _extract_conn_attributes(
        conn.connection_pool.connection_kwargs,
        db_sem_conv_opt_in_mode,
        http_sem_conv_opt_in_mode,
    ).items():
        span.set_attribute(key, value)


def _build_span_name(
    instance: RedisInstance | AsyncRedisInstance, cmd_args: tuple[Any, ...]
) -> str:
    if len(cmd_args) > 0 and cmd_args[0]:
        if cmd_args[0] == "FT.SEARCH":
            name = "redis.search"
        elif cmd_args[0] == "FT.CREATE":
            name = "redis.create_index"
        else:
            name = cmd_args[0]
    else:
        name = instance.connection_pool.connection_kwargs.get("db", 0)
    return name


def _add_create_attributes(span: Span, args: tuple[Any, ...]):
    _set_span_attribute_if_value(
        span, "redis.create_index.index", _value_or_none(args, 1)
    )
    # According to: https://github.com/redis/redis-py/blob/master/redis/commands/search/commands.py#L155 schema is last argument for execute command
    try:
        schema_index = args.index("SCHEMA")
    except ValueError:
        return
    schema = args[schema_index:]
    field_attribute = ""
    # Schema in format:
    # [first_field_name, first_field_type, first_field_some_attribute1, first_field_some_attribute2, second_field_name, ...]
    field_attribute = "".join(
        f"Field(name: {schema[index - 1]}, type: {schema[index]});"
        for index in range(1, len(schema))
        if schema[index] in _FIELD_TYPES
    )
    _set_span_attribute_if_value(
        span,
        "redis.create_index.fields",
        field_attribute,
    )


def _add_search_attributes(span: Span, response, args):
    _set_span_attribute_if_value(
        span, "redis.search.index", _value_or_none(args, 1)
    )
    _set_span_attribute_if_value(
        span, "redis.search.query", _value_or_none(args, 2)
    )
    # Parse response from search
    # https://redis.io/docs/latest/commands/ft.search/
    # Response in format:
    # [number_of_returned_documents, index_of_first_returned_doc, first_doc(as a list), index_of_second_returned_doc, second_doc(as a list) ...]
    # Returned documents in array format:
    # [first_field_name, first_field_value, second_field_name, second_field_value ...]
    number_of_returned_documents = _value_or_none(response, 0)
    _set_span_attribute_if_value(
        span, "redis.search.total", number_of_returned_documents
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
                    f"redis.search.xdoc_{document_index}.{document[attribute_name_index]}",
                    document[attribute_name_index + 1],
                )


def _build_span_meta_data_for_pipeline(
    instance: PipelineInstance | AsyncPipelineInstance,
) -> tuple[list[Any], str, str]:
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

    return command_stack, resource, span_name or "redis"
