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

.. _valkey: https://pypi.org/project/valkey/


Instrument All Clients
----------------------

The easiest way to instrument all valkey client instances is by
``ValkeyInstrumentor().instrument()``:

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey


    # Instrument valkey
    ValkeyInstrumentor().instrument()

    # This will report a span with the default settings
    client = valkey.StrictValkey(host="localhost", port=6379)
    client.get("my-key")

Async Valkey clients (i.e. ``valkey.asyncio.Valkey``) are also instrumented in the same way:

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey.asyncio


    # Instrument valkey
    ValkeyInstrumentor().instrument()

    # This will report a span with the default settings
    async def valkey_get():
        client = valkey.asyncio.Valkey(host="localhost", port=6379)
        await client.get("my-key")

.. note::
    Calling the ``instrument`` method will instrument the client classes, so any client
    created after the ``instrument`` call will be instrumented. To instrument only a
    single client, use :func:`ValkeyInstrumentor.instrument_client` method.

Instrument Single Client
------------------------

The :func:`ValkeyInstrumentor.instrument_client` can instrument a connection instance. This is useful when there are multiple clients with a different valkey database index.
Or, you might have a different connection pool used for an application function you
don't want instrumented.

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    import valkey

    instrumented_client = valkey.Valkey()
    not_instrumented_client = valkey.Valkey()

    # Instrument valkey
    ValkeyInstrumentor.instrument_client(client=instrumented_client)

    # This will report a span with the default settings
    instrumented_client.get("my-key")

    # This will not have a span
    not_instrumented_client.get("my-key")

.. warning::
    All client instances created after calling ``ValkeyInstrumentor().instrument`` will
    be instrumented. To avoid instrumenting all clients, use
    :func:`ValkeyInstrumentor.instrument_client` .

Request/Response Hooks
----------------------

.. code:: python

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

Suppress Instrumentation
------------------------

You can use the ``suppress_instrumentation`` context manager to prevent instrumentation
from being applied to specific Valkey operations. This is useful when you want to avoid
creating spans for internal operations, health checks, or during specific code paths.

.. code:: python

    from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
    from opentelemetry.instrumentation.utils import suppress_instrumentation
    import valkey

    # Instrument valkey
    ValkeyInstrumentor().instrument()

    client = valkey.StrictValkey(host="localhost", port=6379)

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
from typing import TYPE_CHECKING, Any, Callable, Collection

import valkey
import valkey.asyncio
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation._redis_valkey import (
    KVStoreConfig,
    _async_traced_execute_factory,
    _async_traced_execute_pipeline_factory,
    _traced_execute_factory,
    _traced_execute_pipeline_factory,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.valkey.package import _instruments
from opentelemetry.instrumentation.valkey.version import __version__
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Span, TracerProvider, get_tracer

if TYPE_CHECKING:
    import valkey.asyncio.client
    import valkey.asyncio.cluster
    import valkey.client
    import valkey.cluster
    import valkey.connection


_logger = logging.getLogger(__name__)

_INSTRUMENTATION_ATTR = "_is_instrumented_by_opentelemetry"

_VALKEY_CONFIG = KVStoreConfig(
    backend_name="valkey",
    db_system="valkey",
    db_system_attr=SpanAttributes.DB_SYSTEM,
    db_index_attr="db.valkey.database_index",
    args_length_attr="db.valkey.args_length",
    pipeline_length_attr="db.valkey.pipeline_length",
    watch_error_class=valkey.WatchError,
)


# pylint: disable=R0915
def _instrument(
    tracer,
    request_hook=None,
    response_hook=None,
):
    _traced_execute_command = _traced_execute_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )

    wrap_function_wrapper(
        "valkey", "Valkey.execute_command", _traced_execute_command
    )
    wrap_function_wrapper(
        "valkey.client",
        "Pipeline.execute",
        _traced_execute_pipeline,
    )
    wrap_function_wrapper(
        "valkey.client",
        "Pipeline.immediate_execute_command",
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

    _async_traced_execute_command = _async_traced_execute_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )

    wrap_function_wrapper(
        "valkey.asyncio",
        "Valkey.execute_command",
        _async_traced_execute_command,
    )
    wrap_function_wrapper(
        "valkey.asyncio.client",
        "Pipeline.execute",
        _async_traced_execute_pipeline,
    )
    wrap_function_wrapper(
        "valkey.asyncio.client",
        "Pipeline.immediate_execute_command",
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


def _instrument_client(
    client,
    tracer,
    request_hook=None,
    response_hook=None,
):
    _async_traced_execute = _async_traced_execute_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )
    _async_traced_execute_pipeline = _async_traced_execute_pipeline_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )

    if isinstance(client, valkey.asyncio.Valkey):

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

    if isinstance(client, valkey.asyncio.ValkeyCluster):

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

    _traced_execute = _traced_execute_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
    )
    _traced_execute_pipeline = _traced_execute_pipeline_factory(
        _VALKEY_CONFIG, tracer, request_hook, response_hook
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


class ValkeyInstrumentor(BaseInstrumentor):
    """An instrumentor for Valkey.

    See `BaseInstrumentor`
    """

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
        request_hook: Callable | None = None,
        response_hook: Callable | None = None,
        **kwargs,
    ):
        """Instruments all Valkey/StrictValkey/ValkeyCluster and async client instances.

        Args:
            tracer_provider: A TracerProvider, defaults to global.
            request_hook:
                a function with extra user-defined logic to run before performing the request.

                The ``args`` is a tuple, where items are
                command arguments. For example ``client.set("mykey", "value", ex=5)`` would
                have ``args`` as ``('SET', 'mykey', 'value', 'EX', 5)``.

                The ``kwargs`` represents occasional ``options`` passed by valkey. For example,
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
        """Instruments the valkey module

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

    @staticmethod
    def instrument_client(
        client: valkey.Valkey
        | valkey.asyncio.Valkey
        | valkey.cluster.ValkeyCluster
        | valkey.asyncio.ValkeyCluster,
        tracer_provider: TracerProvider | None = None,
        request_hook: Callable | None = None,
        response_hook: Callable | None = None,
    ):
        """Instrument the provided Valkey Client. The client can be sync or async.
        Cluster client is also supported.

        Args:
            client: The valkey client.
            tracer_provider: A TracerProvider, defaults to global.
            request_hook: a function with extra user-defined logic to run before
                performing the request.
            response_hook: a function with extra user-defined logic to run after
                the request is complete.
        """
        if not hasattr(client, _INSTRUMENTATION_ATTR):
            setattr(client, _INSTRUMENTATION_ATTR, False)
        if not getattr(client, _INSTRUMENTATION_ATTR):
            _instrument_client(
                client,
                ValkeyInstrumentor._get_tracer(tracer_provider=tracer_provider),
                request_hook=request_hook,
                response_hook=response_hook,
            )
            setattr(client, _INSTRUMENTATION_ATTR, True)
        else:
            _logger.warning(
                "Attempting to instrument Valkey connection while already instrumented"
            )

    @staticmethod
    def uninstrument_client(
        client: valkey.Valkey
        | valkey.asyncio.Valkey
        | valkey.cluster.ValkeyCluster
        | valkey.asyncio.ValkeyCluster,
    ):
        """Disables instrumentation for the given client instance

        Args:
            client: The valkey client
        """
        if getattr(client, _INSTRUMENTATION_ATTR):
            unwrap(client, "execute_command")
            unwrap(client, "pipeline")
        else:
            _logger.warning(
                "Attempting to un-instrument Valkey connection that wasn't instrumented"
            )
            return

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
