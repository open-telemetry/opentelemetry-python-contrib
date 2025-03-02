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
Instrument `redis`_ to report Redis queries.

.. _redis: https://pypi.org/project/redis/


Instrument All Clients
----------------------

The easiest way to instrument all redis client instances is by
``RedisInstrumentor().instrument()``:

.. code:: python

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    import redis


    # Instrument redis
    RedisInstrumentor().instrument()

    # This will report a span with the default settings
    client = redis.StrictRedis(host="localhost", port=6379)
    client.get("my-key")

Async Redis clients (i.e. ``redis.asyncio.Redis``) are also instrumented in the same way:

.. code:: python

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    import redis.asyncio


    # Instrument redis
    RedisInstrumentor().instrument()

    # This will report a span with the default settings
    async def redis_get():
        client = redis.asyncio.Redis(host="localhost", port=6379)
        await client.get("my-key")

.. note::
    Calling the ``instrument`` method will instrument the client classes, so any client
    created after the ``instrument`` call will be instrumented. To instrument only a
    single client, use :func:`RedisInstrumentor.instrument_client` method.

Instrument Single Client
------------------------

The :func:`RedisInstrumentor.instrument_client` can instrument a connection instance. This is useful when there are multiple clients with a different redis database index.
Or, you might have a different connection pool used for an application function you
don't want instrumented.

.. code:: python

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    import redis

    instrumented_client = redis.Redis()
    not_instrumented_client = redis.Redis()

    # Instrument redis
    RedisInstrumentor.instrument_client(client=instrumented_client)

    # This will report a span with the default settings
    instrumented_client.get("my-key")

    # This will not have a span
    not_instrumented_client.get("my-key")

.. warning::
    All client instances created after calling ``RedisInstrumentor().instrument`` will
    be instrumented. To avoid instrumenting all clients, use
    :func:`RedisInstrumentor.instrument_client` .

Request/Response Hooks
----------------------

.. code:: python

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    import redis

    def request_hook(span, instance, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span, instance, response):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    # Instrument redis with hooks
    RedisInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook)

    # This will report a span with the default settings and the custom attributes added from the hooks
    client = redis.StrictRedis(host="localhost", port=6379)
    client.get("my-key")

API
---
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Collection

import redis
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.redis.package import _instruments
from opentelemetry.instrumentation.redis.util import (
    _extract_conn_attributes,
    _format_command_args,
    _set_span_attribute_if_value,
    _value_or_none,
)
from opentelemetry.instrumentation.redis.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import (
    Span,
    StatusCode,
    Tracer,
    TracerProvider,
    get_tracer,
)

if TYPE_CHECKING:
    from typing import Awaitable, TypeVar

    import redis.asyncio.client
    import redis.asyncio.cluster
    import redis.client
    import redis.cluster
    import redis.connection

    RequestHook = Callable[
        [Span, redis.connection.Connection, list[Any], dict[str, Any]], None
    ]
    ResponseHook = Callable[[Span, redis.connection.Connection, Any], None]

    AsyncPipelineInstance = TypeVar(
        "AsyncPipelineInstance",
        redis.asyncio.client.Pipeline,
        redis.asyncio.cluster.ClusterPipeline,
    )
    AsyncRedisInstance = TypeVar(
        "AsyncRedisInstance", redis.asyncio.Redis, redis.asyncio.RedisCluster
    )
    PipelineInstance = TypeVar(
        "PipelineInstance",
        redis.client.Pipeline,
        redis.cluster.ClusterPipeline,
    )
    RedisInstance = TypeVar(
        "RedisInstance", redis.client.Redis, redis.cluster.RedisCluster
    )
    R = TypeVar("R")


_DEFAULT_SERVICE = "redis"
_logger = logging.getLogger(__name__)

_REDIS_ASYNCIO_VERSION = (4, 2, 0)
_REDIS_CLUSTER_VERSION = (4, 1, 0)
_REDIS_ASYNCIO_CLUSTER_VERSION = (4, 3, 2)

_FIELD_TYPES = ["NUMERIC", "TEXT", "GEO", "TAG", "VECTOR"]

_CLIENT_ASYNCIO_SUPPORT = redis.VERSION >= _REDIS_ASYNCIO_VERSION
_CLIENT_ASYNCIO_CLUSTER_SUPPORT = (
    redis.VERSION >= _REDIS_ASYNCIO_CLUSTER_VERSION
)
_CLIENT_CLUSTER_SUPPORT = redis.VERSION >= _REDIS_CLUSTER_VERSION
_CLIENT_BEFORE_3_0_0 = redis.VERSION < (3, 0, 0)

if _CLIENT_ASYNCIO_SUPPORT:
    import redis.asyncio

INSTRUMENTATION_ATTR = "_is_instrumented_by_opentelemetry"


def _set_connection_attributes(
    span: Span, conn: RedisInstance | AsyncRedisInstance
) -> None:
    if not span.is_recording() or not hasattr(conn, "connection_pool"):
        return
    for key, value in _extract_conn_attributes(
        conn.connection_pool.connection_kwargs
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

    return command_stack, resource, span_name


def _traced_execute_factory(
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
    def _traced_execute_command(
        func: Callable[..., R],
        instance: RedisInstance,
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
                span.set_attribute("db.redis.args_length", len(args))
                if span.name == "redis.create_index":
                    _add_create_attributes(span, args)
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = func(*args, **kwargs)
            if span.is_recording():
                if span.name == "redis.search":
                    _add_search_attributes(span, response, args)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    return _traced_execute_command


def _traced_execute_pipeline_factory(
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
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
                    "db.redis.pipeline_length", len(command_stack)
                )

            response = None
            try:
                response = func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    return _traced_execute_pipeline


def _async_traced_execute_factory(
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
    async def _async_traced_execute_command(
        func: Callable[..., Awaitable[R]],
        instance: AsyncRedisInstance,
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
                span.set_attribute("db.redis.args_length", len(args))
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = await func(*args, **kwargs)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    return _async_traced_execute_command


def _async_traced_execute_pipeline_factory(
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
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
                    "db.redis.pipeline_length", len(command_stack)
                )

            response = None
            try:
                response = await func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    return _async_traced_execute_pipeline


# pylint: disable=R0915
def _instrument(
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
    _traced_execute_command = _traced_execute_factory(
        tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        tracer, request_hook, response_hook
    )
    pipeline_class = "BasePipeline" if _CLIENT_BEFORE_3_0_0 else "Pipeline"
    redis_class = "StrictRedis" if _CLIENT_BEFORE_3_0_0 else "Redis"

    wrap_function_wrapper(
        "redis", f"{redis_class}.execute_command", _traced_execute_command
    )
    wrap_function_wrapper(
        "redis.client",
        f"{pipeline_class}.execute",
        _traced_execute_pipeline,
    )
    wrap_function_wrapper(
        "redis.client",
        f"{pipeline_class}.immediate_execute_command",
        _traced_execute_command,
    )
    if _CLIENT_CLUSTER_SUPPORT:
        wrap_function_wrapper(
            "redis.cluster",
            "RedisCluster.execute_command",
            _traced_execute_command,
        )
        wrap_function_wrapper(
            "redis.cluster",
            "ClusterPipeline.execute",
            _traced_execute_pipeline,
        )

    _async_traced_execute_command = _async_traced_execute_factory(
        tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        tracer, request_hook, response_hook
    )
    if _CLIENT_ASYNCIO_SUPPORT:
        wrap_function_wrapper(
            "redis.asyncio",
            f"{redis_class}.execute_command",
            _async_traced_execute_command,
        )
        wrap_function_wrapper(
            "redis.asyncio.client",
            f"{pipeline_class}.execute",
            _async_traced_execute_pipeline,
        )
        wrap_function_wrapper(
            "redis.asyncio.client",
            f"{pipeline_class}.immediate_execute_command",
            _async_traced_execute_command,
        )
    if _CLIENT_ASYNCIO_CLUSTER_SUPPORT:
        wrap_function_wrapper(
            "redis.asyncio.cluster",
            "RedisCluster.execute_command",
            _async_traced_execute_command,
        )
        wrap_function_wrapper(
            "redis.asyncio.cluster",
            "ClusterPipeline.execute",
            _async_traced_execute_pipeline,
        )


def _instrument_client(
    client,
    tracer: Tracer,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
):
    # first, handle async clients and cluster clients
    _async_traced_execute = _async_traced_execute_factory(
        tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        tracer, request_hook, response_hook
    )

    if _CLIENT_ASYNCIO_SUPPORT and isinstance(client, redis.asyncio.Redis):

        def _async_pipeline_wrapper(func, instance, args, kwargs):
            result = func(*args, **kwargs)
            wrap_function_wrapper(
                result, "execute", _async_traced_execute_pipeline
            )
            wrap_function_wrapper(
                result, "immediate_execute_command", _async_traced_execute
            )
            return result

        wrap_function_wrapper(client, "execute_command", _async_traced_execute)
        wrap_function_wrapper(client, "pipeline", _async_pipeline_wrapper)
        return

    if _CLIENT_ASYNCIO_CLUSTER_SUPPORT and isinstance(
        client, redis.asyncio.RedisCluster
    ):

        def _async_cluster_pipeline_wrapper(func, instance, args, kwargs):
            result = func(*args, **kwargs)
            wrap_function_wrapper(
                result, "execute", _async_traced_execute_pipeline
            )
            return result

        wrap_function_wrapper(client, "execute_command", _async_traced_execute)
        wrap_function_wrapper(
            client, "pipeline", _async_cluster_pipeline_wrapper
        )
        return
    # for redis.client.Redis, redis.Cluster and v3.0.0 redis.client.StrictRedis
    # the wrappers are the same
    _traced_execute = _traced_execute_factory(
        tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        tracer, request_hook, response_hook
    )

    def _pipeline_wrapper(func, instance, args, kwargs):
        result = func(*args, **kwargs)
        wrap_function_wrapper(result, "execute", _traced_execute_pipeline)
        wrap_function_wrapper(
            result, "immediate_execute_command", _traced_execute
        )
        return result

    wrap_function_wrapper(
        client,
        "execute_command",
        _traced_execute,
    )
    wrap_function_wrapper(
        client,
        "pipeline",
        _pipeline_wrapper,
    )


class RedisInstrumentor(BaseInstrumentor):
    @staticmethod
    def _get_tracer(**kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        return get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

    def instrument(
        self,
        tracer_provider: TracerProvider | None = None,
        request_hook: RequestHook | None = None,
        response_hook: ResponseHook | None = None,
        **kwargs,
    ):
        """Instruments all Redis/StrictRedis/RedisCluster and async client instances.

        Args:
            tracer_provider: A TracerProvider, defaults to global.
            request_hook:
                a function with extra user-defined logic to run before performing the request.

                The ``args`` is a tuple, where items are
                command arguments. For example ``client.set("mykey", "value", ex=5)`` would
                have ``args`` as ``('SET', 'mykey', 'value', 'EX', 5)``.

                The ``kwargs`` represents occasional ``options`` passed by redis. For example,
                if you use ``client.set("mykey", "value", get=True)``, the ``kwargs`` would be
                ``{'get': True}``.
            response_hook:
                a function with extra user-defined logic to run after the request is complete.

                The ``args`` represents the response.
        """
        super().instrument(
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
            **kwargs,
        )

    def _instrument(self, **kwargs: Any):
        """Instruments the redis module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``request_hook``: An optional callback that is invoked right after a span is created.
                ``response_hook``: An optional callback which is invoked right before the span is finished processing a response.
        """
        _instrument(
            self._get_tracer(**kwargs),
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
        )

    def _uninstrument(self, **kwargs: Any):
        if _CLIENT_BEFORE_3_0_0:
            unwrap(redis.StrictRedis, "execute_command")
            unwrap(redis.StrictRedis, "pipeline")
            unwrap(redis.Redis, "pipeline")
            unwrap(
                redis.client.BasePipeline,  # pylint:disable=no-member
                "execute",
            )
            unwrap(
                redis.client.BasePipeline,  # pylint:disable=no-member
                "immediate_execute_command",
            )
        else:
            unwrap(redis.Redis, "execute_command")
            unwrap(redis.Redis, "pipeline")
            unwrap(redis.client.Pipeline, "execute")
            unwrap(redis.client.Pipeline, "immediate_execute_command")
        if _CLIENT_CLUSTER_SUPPORT:
            unwrap(redis.cluster.RedisCluster, "execute_command")
            unwrap(redis.cluster.ClusterPipeline, "execute")
        if _CLIENT_ASYNCIO_SUPPORT:
            unwrap(redis.asyncio.Redis, "execute_command")
            unwrap(redis.asyncio.Redis, "pipeline")
            unwrap(redis.asyncio.client.Pipeline, "execute")
            unwrap(redis.asyncio.client.Pipeline, "immediate_execute_command")
        if _CLIENT_ASYNCIO_CLUSTER_SUPPORT:
            unwrap(redis.asyncio.cluster.RedisCluster, "execute_command")
            unwrap(redis.asyncio.cluster.ClusterPipeline, "execute")

    @staticmethod
    def instrument_client(
        client: redis.StrictRedis
        | redis.Redis
        | redis.asyncio.Redis
        | redis.cluster.RedisCluster
        | redis.asyncio.cluster.RedisCluster,
        tracer_provider: TracerProvider | None = None,
        request_hook: RequestHook | None = None,
        response_hook: ResponseHook | None = None,
    ):
        """Instrument the provided Redis Client. The client can be sync or async.
        Cluster client is also supported.

        Args:
            client: The redis client.
            tracer_provider: A TracerProvider, defaults to global.
            request_hook: a function with extra user-defined logic to run before
                performing the request.

                The ``args`` is a tuple, where items are
                command arguments. For example ``client.set("mykey", "value", ex=5)`` would
                have ``args`` as ``('SET', 'mykey', 'value', 'EX', 5)``.

                The ``kwargs`` represents occasional ``options`` passed by redis. For example,
                if you use ``client.set("mykey", "value", get=True)``, the ``kwargs`` would be
                ``{'get': True}``.

            response_hook: a function with extra user-defined logic to run after
                the request is complete.

                The ``args`` represents the response.
        """
        if not hasattr(client, INSTRUMENTATION_ATTR):
            setattr(client, INSTRUMENTATION_ATTR, False)
        if not getattr(client, INSTRUMENTATION_ATTR):
            _instrument_client(
                client,
                RedisInstrumentor._get_tracer(tracer_provider=tracer_provider),
                request_hook=request_hook,
                response_hook=response_hook,
            )
            setattr(client, INSTRUMENTATION_ATTR, True)
        else:
            _logger.warning(
                "Attempting to instrument Redis connection while already instrumented"
            )

    @staticmethod
    def uninstrument_client(
        client: redis.StrictRedis
        | redis.Redis
        | redis.asyncio.Redis
        | redis.cluster.RedisCluster
        | redis.asyncio.cluster.RedisCluster,
    ):
        """Disables instrumentation for the given client instance

        Args:
            client: The redis client
        """
        if getattr(client, INSTRUMENTATION_ATTR):
            # for all clients we need to unwrap execute_command and pipeline functions
            unwrap(client, "execute_command")
            # the method was creating a pipeline and wrapping the functions of the
            # created instance. any pipelines created before un-instrumenting will
            # remain instrumented (pipelines should usually have a short span)
            unwrap(client, "pipeline")
        else:
            _logger.warning(
                "Attempting to un-instrument Redis connection that wasn't instrumented"
            )
            return

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return a list of python packages with versions that the will be instrumented."""
        return _instruments
