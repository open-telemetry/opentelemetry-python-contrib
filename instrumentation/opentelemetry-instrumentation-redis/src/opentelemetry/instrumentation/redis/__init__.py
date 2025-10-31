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
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.redis.package import _instruments
from opentelemetry.instrumentation.redis.util import (
    _add_create_attributes,
    _add_search_attributes,
    _build_span_meta_data_for_pipeline,
    _build_span_name,
    _format_command_args,
    _set_connection_attributes,
)
from opentelemetry.instrumentation.redis.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_STATEMENT,
)
from opentelemetry.trace import (
    StatusCode,
    Tracer,
    TracerProvider,
    get_tracer,
)

if TYPE_CHECKING:
    from typing import Awaitable

    import redis.asyncio.client
    import redis.asyncio.cluster
    import redis.client
    import redis.cluster
    import redis.connection

    from opentelemetry.instrumentation.redis.custom_types import (
        AsyncPipelineInstance,
        AsyncRedisInstance,
        PipelineInstance,
        R,
        RedisInstance,
        RequestHook,
        ResponseHook,
    )


_logger = logging.getLogger(__name__)

_REDIS_ASYNCIO_VERSION = (4, 2, 0)
_REDIS_CLUSTER_VERSION = (4, 1, 0)
_REDIS_ASYNCIO_CLUSTER_VERSION = (4, 3, 2)


_CLIENT_ASYNCIO_SUPPORT = redis.VERSION >= _REDIS_ASYNCIO_VERSION
_CLIENT_ASYNCIO_CLUSTER_SUPPORT = (
    redis.VERSION >= _REDIS_ASYNCIO_CLUSTER_VERSION
)
_CLIENT_CLUSTER_SUPPORT = redis.VERSION >= _REDIS_CLUSTER_VERSION
_CLIENT_BEFORE_V3 = redis.VERSION < (3, 0, 0)

if _CLIENT_ASYNCIO_SUPPORT:
    import redis.asyncio

_INSTRUMENTATION_ATTR = "_is_instrumented_by_opentelemetry"


def _get_redis_conn_info(instance):
    host, port, db, unix_sock = None, None, None, None
    pool = getattr(instance, "connection_pool", None)
    if pool:
        conn_kwargs = pool.connection_kwargs
        host = conn_kwargs.get("host")
        port = conn_kwargs.get("port")
        db = conn_kwargs.get("db", 0)
        unix_sock = conn_kwargs.get("path")
    return host, port, db, unix_sock


# Helper function to set old semantic convention attributes
def _set_old_semconv_attributes(
    span,
    instance,
    args,
    query,
    command_stack,
    resource,
    is_pipeline,
):
    span.set_attribute(DB_STATEMENT, query if not is_pipeline else resource)
    _set_connection_attributes(span, instance)
    if not is_pipeline:
        span.set_attribute("db.redis.args_length", len(args))
    else:
        span.set_attribute("db.redis.pipeline_length", len(command_stack))


# Helper function to set new semantic convention attributes
def _set_new_semconv_attributes(
    span,
    instance,
    args,
    query,
    command_stack,
    resource,
    is_pipeline,
):
    span.set_attribute("db.system.name", "redis")

    if not is_pipeline:
        if args and len(args) > 0:
            span.set_attribute("db.operation.name", args[0])
    else:
        span.set_attribute("db.operation.name", "PIPELINE")
        if len(command_stack) > 1:
            span.set_attribute("db.operation.batch.size", len(command_stack))

    host, port, db, unix_sock = _get_redis_conn_info(instance)
    if db is not None:
        span.set_attribute("db.namespace", str(db))
    span.set_attribute("db.query.text", query if not is_pipeline else resource)
    if host:
        span.set_attribute("server.address", host)
        span.set_attribute("network.peer.address", host)
    if port:
        span.set_attribute("server.port", port)
        span.set_attribute("network.peer.port", port)
    if unix_sock:
        span.set_attribute("network.peer.address", unix_sock)
        span.set_attribute("network.transport", "unix")

    # db.stored_procedure.name (only for individual commands)
    if not is_pipeline:
        if args and args[0] in ("EVALSHA", "FCALL") and len(args) > 1:
            span.set_attribute("db.stored_procedure.name", args[1])


# Helper function to set all common span attributes
def _set_span_attributes(
    span,
    instance,
    args,  # For individual commands
    query,  # For individual commands
    command_stack,  # For pipelines
    resource,  # For pipelines
    semconv_opt_in_mode,
):
    if not span.is_recording():
        return

    is_pipeline = command_stack is not None

    if _report_old(semconv_opt_in_mode):
        _set_old_semconv_attributes(
            span, instance, args, query, command_stack, resource, is_pipeline
        )

    if _report_new(semconv_opt_in_mode):
        _set_new_semconv_attributes(
            span, instance, args, query, command_stack, resource, is_pipeline
        )

    # Command-specific attributes that depend on span.name (e.g., redis.create_index)
    if not is_pipeline and span.name == "redis.create_index":
        _add_create_attributes(span, args)


# Helper function to set error attributes on a span
def _set_span_error_attributes(span, exc, semconv_opt_in_mode):
    if not span.is_recording():
        return

    if _report_new(semconv_opt_in_mode):
        error_type = getattr(exc, "args", [None])[0]
        if error_type and isinstance(error_type, str):
            prefix = error_type.split(" ")[0]
            span.set_attribute("db.response.status_code", prefix)
            span.set_attribute("error.type", prefix)
        else:
            span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(StatusCode.ERROR)


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
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE
        )
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            _set_span_attributes(
                span, instance, args, query, None, None, semconv_opt_in_mode
            )

            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            try:
                response = func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                if span.is_recording():
                    span.set_status(StatusCode.UNSET)
                raise watch_exception
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _set_span_error_attributes(span, exc, semconv_opt_in_mode)
                raise
            if span.is_recording() and span.name == "redis.search":
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
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE
        )
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            _set_span_attributes(
                span,
                instance,
                None,
                None,
                command_stack,
                resource,
                semconv_opt_in_mode,
            )

            response = None
            try:
                response = func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                if span.is_recording():
                    span.set_status(StatusCode.UNSET)
                exception = watch_exception
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _set_span_error_attributes(span, exc, semconv_opt_in_mode)
                exception = exc

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
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE
        )
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            _set_span_attributes(
                span, instance, args, query, None, None, semconv_opt_in_mode
            )

            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            try:
                response = await func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                if span.is_recording():
                    span.set_status(StatusCode.UNSET)
                raise watch_exception
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _set_span_error_attributes(span, exc, semconv_opt_in_mode)
                raise
            if span.is_recording() and span.name == "redis.search":
                _add_search_attributes(span, response, args)
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
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE
        )
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            _set_span_attributes(
                span,
                instance,
                None,
                None,
                command_stack,
                resource,
                semconv_opt_in_mode,
            )

            response = None
            try:
                response = await func(*args, **kwargs)
            except redis.WatchError as watch_exception:
                if span.is_recording():
                    span.set_status(StatusCode.UNSET)
                exception = watch_exception
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _set_span_error_attributes(span, exc, semconv_opt_in_mode)
                exception = exc

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception is not None:
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
    pipeline_class = "BasePipeline" if _CLIENT_BEFORE_V3 else "Pipeline"
    redis_class = "StrictRedis" if _CLIENT_BEFORE_V3 else "Redis"

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
        if _CLIENT_BEFORE_V3:
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
        if not hasattr(client, _INSTRUMENTATION_ATTR):
            setattr(client, _INSTRUMENTATION_ATTR, False)
        if not getattr(client, _INSTRUMENTATION_ATTR):
            _instrument_client(
                client,
                RedisInstrumentor._get_tracer(tracer_provider=tracer_provider),
                request_hook=request_hook,
                response_hook=response_hook,
            )
            setattr(client, _INSTRUMENTATION_ATTR, True)
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
        if getattr(client, _INSTRUMENTATION_ATTR):
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
