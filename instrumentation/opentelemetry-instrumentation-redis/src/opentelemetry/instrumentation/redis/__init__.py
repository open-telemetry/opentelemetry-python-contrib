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

Suppress Instrumentation
------------------------

You can use the ``suppress_instrumentation`` context manager to prevent instrumentation
from being applied to specific Redis operations. This is useful when you want to avoid
creating spans for internal operations, health checks, or during specific code paths.

.. code:: python

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.utils import suppress_instrumentation
    import redis

    # Instrument redis
    RedisInstrumentor().instrument()

    client = redis.StrictRedis(host="localhost", port=6379)

    # This will report a span
    client.get("my-key")

    # This will NOT report a span
    with suppress_instrumentation():
        client.get("internal-key")
        client.set("cache-key", "value")

    # This will report a span again
    client.get("another-key")

API
---
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Collection

import redis
from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation._redis_valkey import (
    KVStoreConfig,
    _async_traced_execute_factory,
    _async_traced_execute_pipeline_factory,
    _traced_execute_factory,
    _traced_execute_pipeline_factory,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.redis.package import _instruments
from opentelemetry.instrumentation.redis.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_REDIS_DATABASE_INDEX,
    DB_SYSTEM,
)
from opentelemetry.semconv.trace import DbSystemValues
from opentelemetry.trace import TracerProvider, get_tracer

if TYPE_CHECKING:
    from opentelemetry.instrumentation.redis.custom_types import (
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

_REDIS_CONFIG = KVStoreConfig(
    backend_name="redis",
    db_system=DbSystemValues.REDIS.value,
    db_system_attr=DB_SYSTEM,
    db_index_attr=DB_REDIS_DATABASE_INDEX,
    args_length_attr="db.redis.args_length",
    pipeline_length_attr="db.redis.pipeline_length",
    watch_error_class=redis.WatchError,
)


# pylint: disable=R0915
def _instrument(
    tracer,
    request_hook=None,
    response_hook=None,
):
    _traced_execute_command = _traced_execute_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
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
        _REDIS_CONFIG, tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
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
    tracer,
    request_hook=None,
    response_hook=None,
):
    # first, handle async clients and cluster clients
    _async_traced_execute = _async_traced_execute_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
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
        _REDIS_CONFIG, tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        _REDIS_CONFIG, tracer, request_hook, response_hook
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
