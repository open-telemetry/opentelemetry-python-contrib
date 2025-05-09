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
Instrument `valkey`_ to report Valkey queries.

There are two options for instrumenting code. The first option is to use the
``opentelemetry-instrument`` executable which will automatically
instrument your Valkey client. The second is to programmatically enable
instrumentation via the following code:

.. _valkey: https://pypi.org/project/valkey/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey


    # Instrument valkey
    ValkeyInstrumentor().instrument()

    # This will report a span with the default settings
    client = valkey.StrictValkey(host="localhost", port=6379)
    client.get("my-key")

Async Valkey clients (i.e. valkey.asyncio.Valkey) are also instrumented in the same way:

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey.asyncio


    # Instrument valkey
    ValkeyInstrumentor().instrument()

    # This will report a span with the default settings
    async def valkey_get():
        client = valkey.asyncio.Valkey(host="localhost", port=6379)
        await client.get("my-key")

The `instrument` method accepts the following keyword args:

tracer_provider (TracerProvider) - an optional tracer provider

request_hook (Callable) - a function with extra user-defined logic to be performed before performing the request
this function signature is:  def request_hook(span: Span, instance: valkey.connection.Connection, args, kwargs) -> None

response_hook (Callable) - a function with extra user-defined logic to be performed after performing the request
this function signature is: def response_hook(span: Span, instance: valkey.connection.Connection, response) -> None

for example:

.. code: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey

    def request_hook(span, instance, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span, instance, response):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    # Instrument valkey with hooks
    ValkeyInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook)

    # This will report a span with the default settings and the custom attributes added from the hooks
    client = valkey.StrictValkey(host="localhost", port=6379)
    client.get("my-key")


API
---
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Collection

import valkey
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.valkey.package import _instruments
from opentelemetry.instrumentation.valkey.util import (
    _extract_conn_attributes,
    _format_command_args,
    _set_span_attribute_if_value,
    _value_or_none,
)
from opentelemetry.instrumentation.valkey.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Span, StatusCode, Tracer

if TYPE_CHECKING:
    from typing import Awaitable, TypeVar

    import valkey.asyncio.client
    import valkey.asyncio.cluster
    import valkey.client
    import valkey.cluster
    import valkey.connection

    _RequestHookT = Callable[
        [Span, valkey.connection.Connection, list[Any], dict[str, Any]], None
    ]
    _ResponseHookT = Callable[[Span, valkey.connection.Connection, Any], None]

    AsyncPipelineInstance = TypeVar(
        "AsyncPipelineInstance",
        valkey.asyncio.client.Pipeline,
        valkey.asyncio.cluster.ClusterPipeline,
    )
    AsyncValkeyInstance = TypeVar(
        "AsyncValkeyInstance", valkey.asyncio.Valkey, valkey.asyncio.ValkeyCluster
    )
    PipelineInstance = TypeVar(
        "PipelineInstance",
        valkey.client.Pipeline,
        valkey.cluster.ClusterPipeline,
    )
    ValkeyInstance = TypeVar(
        "ValkeyInstance", valkey.client.Valkey, valkey.cluster.ValkeyCluster
    )
    R = TypeVar("R")


_DEFAULT_SERVICE = "valkey"


import valkey.asyncio

_FIELD_TYPES = ["NUMERIC", "TEXT", "GEO", "TAG", "VECTOR"]


def _set_connection_attributes(
    span: Span, conn: ValkeyInstance | AsyncValkeyInstance
) -> None:
    if not span.is_recording() or not hasattr(conn, "connection_pool"):
        return
    for key, value in _extract_conn_attributes(
        conn.connection_pool.connection_kwargs
    ).items():
        span.set_attribute(key, value)


def _build_span_name(
    instance: ValkeyInstance | AsyncValkeyInstance, cmd_args: tuple[Any, ...]
) -> str:
    if len(cmd_args) > 0 and cmd_args[0]:
        if cmd_args[0] == "FT.SEARCH":
            name = "valkey.search"
        elif cmd_args[0] == "FT.CREATE":
            name = "valkey.create_index"
        else:
            name = cmd_args[0]
    else:
        name = instance.connection_pool.connection_kwargs.get("db", 0)
    return name


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

    return command_stack, resource, span_name


# pylint: disable=R0915
def _instrument(
    tracer: Tracer,
    request_hook: _RequestHookT | None = None,
    response_hook: _ResponseHookT | None = None,
):
    def _traced_execute_command(
        func: Callable[..., R],
        instance: ValkeyInstance,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        query = _format_command_args(args)
        name = _build_span_name(instance, args)
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.DB_STATEMENT, query)
                _set_connection_attributes(span, instance)
                span.set_attribute("db.valkey.args_length", len(args))
                if span.name == "valkey.create_index":
                    _add_create_attributes(span, args)
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = func(*args, **kwargs)
            if span.is_recording():
                if span.name == "valkey.search":
                    _add_search_attributes(span, response, args)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    def _traced_execute_pipeline(
        func: Callable[..., R],
        instance: PipelineInstance,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        (
            command_stack,
            resource,
            span_name,
        ) = _build_span_meta_data_for_pipeline(instance)
        exception = None
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.DB_STATEMENT, resource)
                _set_connection_attributes(span, instance)
                span.set_attribute(
                    "db.valkey.pipeline_length", len(command_stack)
                )

            response = None
            try:
                response = func(*args, **kwargs)
            except valkey.WatchError as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    def _add_create_attributes(span: Span, args: tuple[Any, ...]):
        _set_span_attribute_if_value(
            span, "valkey.create_index.index", _value_or_none(args, 1)
        )
        # According to: https://github.com/valkey/valkey-py/blob/master/valkey/commands/search/commands.py#L155 schema is last argument for execute command
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
            "valkey.create_index.fields",
            field_attribute,
        )

    def _add_search_attributes(span: Span, response, args):
        _set_span_attribute_if_value(
            span, "valkey.search.index", _value_or_none(args, 1)
        )
        _set_span_attribute_if_value(
            span, "valkey.search.query", _value_or_none(args, 2)
        )
        # Parse response from search
        # https://github.com/valkey-io/valkey-search/blob/main/COMMANDS.md#ftsearch
        # Response in format:
        # [number_of_returned_documents, index_of_first_returned_doc, first_doc(as a list), index_of_second_returned_doc, second_doc(as a list) ...]
        # Returned documents in array format:
        # [first_field_name, first_field_value, second_field_name, second_field_value ...]
        number_of_returned_documents = _value_or_none(response, 0)
        _set_span_attribute_if_value(
            span, "valkey.search.total", number_of_returned_documents
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
                        f"valkey.search.xdoc_{document_index}.{document[attribute_name_index]}",
                        document[attribute_name_index + 1],
                    )

    pipeline_class = "Pipeline"
    valkey_class = "Valkey"

    wrap_function_wrapper(
        "valkey", f"{valkey_class}.execute_command", _traced_execute_command
    )
    wrap_function_wrapper(
        "valkey.client",
        f"{pipeline_class}.execute",
        _traced_execute_pipeline,
    )
    wrap_function_wrapper(
        "valkey.client",
        f"{pipeline_class}.immediate_execute_command",
        _traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.cluster",
        "ValkeyCluster.execute_command",
        _traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.cluster",
        "ClusterPipeline.execute",
        _traced_execute_pipeline,
    )

    async def _async_traced_execute_command(
        func: Callable[..., Awaitable[R]],
        instance: AsyncValkeyInstance,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Awaitable[R]:
        query = _format_command_args(args)
        name = _build_span_name(instance, args)

        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.DB_STATEMENT, query)
                _set_connection_attributes(span, instance)
                span.set_attribute("db.valkey.args_length", len(args))
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = await func(*args, **kwargs)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    async def _async_traced_execute_pipeline(
        func: Callable[..., Awaitable[R]],
        instance: AsyncPipelineInstance,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Awaitable[R]:
        (
            command_stack,
            resource,
            span_name,
        ) = _build_span_meta_data_for_pipeline(instance)

        exception = None

        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.DB_STATEMENT, resource)
                _set_connection_attributes(span, instance)
                span.set_attribute(
                    "db.valkey.pipeline_length", len(command_stack)
                )

            response = None
            try:
                response = await func(*args, **kwargs)
            except valkey.WatchError as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    wrap_function_wrapper(
        "valkey.asyncio",
        f"{valkey_class}.execute_command",
        _async_traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.asyncio.client",
        f"{pipeline_class}.execute",
        _async_traced_execute_pipeline,
    )
    wrap_function_wrapper(
        "valkey.asyncio.client",
        f"{pipeline_class}.immediate_execute_command",
        _async_traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.asyncio.cluster",
        "ValkeyCluster.execute_command",
        _async_traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.asyncio.cluster",
        "ClusterPipeline.execute",
        _async_traced_execute_pipeline,
    )


class ValkeyInstrumentor(BaseInstrumentor):
    """An instrumentor for Valkey.

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """Instruments the valkey module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``request_hook``: An optional callback that is invoked right after a span is created.
                ``response_hook``: An optional callback which is invoked right before the span is finished processing a response.
        """
        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        _instrument(
            tracer,
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
        )

    def _uninstrument(self, **kwargs: Any):
        unwrap(valkey.Valkey, "execute_command")
        unwrap(valkey.Valkey, "pipeline")
        unwrap(valkey.client.Pipeline, "execute")
        unwrap(valkey.client.Pipeline, "immediate_execute_command")
        unwrap(valkey.cluster.ValkeyCluster, "execute_command")
        unwrap(valkey.cluster.ClusterPipeline, "execute")
        unwrap(valkey.asyncio.Valkey, "execute_command")
        unwrap(valkey.asyncio.Valkey, "pipeline")
        unwrap(valkey.asyncio.client.Pipeline, "execute")
        unwrap(valkey.asyncio.client.Pipeline, "immediate_execute_command")
        unwrap(valkey.asyncio.cluster.ValkeyCluster, "execute_command")
        unwrap(valkey.asyncio.cluster.ClusterPipeline, "execute")
