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

"""
Instrument `aerospike`_ to report Aerospike database queries.

.. _aerospike: https://pypi.org/project/aerospike/


Usage
-----

The easiest way to instrument Aerospike clients is by calling
``AerospikeInstrumentor().instrument()``:

.. code:: python

    import aerospike
    from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor

    # Instrument aerospike
    AerospikeInstrumentor().instrument()

    config = {'hosts': [('127.0.0.1', 3000)]}
    client = aerospike.client(config)
    client.connect()

    # All subsequent operations will be traced
    client.put(('test', 'demo', 'key1'), {'bin1': 'value1'})
    (key, meta, bins) = client.get(('test', 'demo', 'key1'))

.. note::
    Calling the ``instrument`` method will wrap the ``aerospike.client()`` factory
    function, so any client created after the ``instrument`` call will be instrumented.


Usage with Custom Tracer Provider
---------------------------------

You can optionally provide a custom tracer provider:

.. code:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor
    import aerospike

    # Set up a custom tracer provider
    provider = TracerProvider()
    trace.set_tracer_provider(provider)

    # Instrument with custom tracer provider
    AerospikeInstrumentor().instrument(tracer_provider=provider)

    config = {'hosts': [('127.0.0.1', 3000)]}
    client = aerospike.client(config)
    client.connect()


Request/Response Hooks
----------------------

You can customize span attributes using request, response, and error hooks:

.. code:: python

    from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor
    import aerospike

    def request_hook(span, operation, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span, operation, result):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    def error_hook(span, operation, exception):
        if span and span.is_recording():
            span.set_attribute("aerospike.error.code", getattr(exception, 'code', -1))

    # Instrument aerospike with hooks
    AerospikeInstrumentor().instrument(
        request_hook=request_hook,
        response_hook=response_hook,
        error_hook=error_hook,
    )

    config = {'hosts': [('127.0.0.1', 3000)]}
    client = aerospike.client(config)
    client.connect()

    # This will report a span with custom attributes
    client.get(('test', 'demo', 'key1'))


Capture Record Keys
-------------------

By default, record keys are not captured in span attributes for security reasons.
If you need to capture keys for debugging purposes, you can enable this feature:

.. code:: python

    from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor
    import aerospike

    # Enable key capture (use with caution)
    AerospikeInstrumentor().instrument(capture_key=True)

    config = {'hosts': [('127.0.0.1', 3000)]}
    client = aerospike.client(config)
    client.connect()

    # The key 'user123' will be captured in the span as 'db.aerospike.key'
    client.get(('test', 'users', 'user123'))

.. warning::
    Enabling ``capture_key`` may expose sensitive data in your traces.
    Only enable this option in development or when you are certain that
    record keys do not contain personally identifiable information (PII)
    or other sensitive data.


Suppress Instrumentation
------------------------

You can use the ``suppress_instrumentation`` context manager to prevent instrumentation
from being applied to specific Aerospike operations. This is useful when you want to avoid
creating spans for internal operations, health checks, or during specific code paths.

.. code:: python

    from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor
    from opentelemetry.instrumentation.utils import suppress_instrumentation
    import aerospike

    # Instrument aerospike
    AerospikeInstrumentor().instrument()

    config = {'hosts': [('127.0.0.1', 3000)]}
    client = aerospike.client(config)
    client.connect()

    # This will report a span
    client.get(('test', 'demo', 'key1'))

    # This will NOT report a span
    with suppress_instrumentation():
        client.get(('test', 'demo', 'internal-key'))
        client.put(('test', 'demo', 'cache-key'), {'data': 'value'})

    # This will report a span again
    client.get(('test', 'demo', 'another-key'))


API
---
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Collection
from typing import Any

from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.aerospike.package import _instruments
from opentelemetry.instrumentation.aerospike.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    is_instrumentation_enabled,
    unwrap,
)
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

# Semantic convention constants
_DB_SYSTEM = "aerospike"
_DB_SYSTEM_ATTR = "db.system"
_DB_NAMESPACE_ATTR = "db.namespace"
_DB_COLLECTION_NAME_ATTR = "db.collection.name"
_DB_OPERATION_NAME_ATTR = "db.operation.name"
_DB_OPERATION_BATCH_SIZE_ATTR = "db.operation.batch.size"
_DB_RESPONSE_STATUS_CODE_ATTR = "db.response.status_code"
_SERVER_ADDRESS_ATTR = "server.address"
_SERVER_PORT_ATTR = "server.port"
_ERROR_TYPE_ATTR = "error.type"

# Aerospike-specific attributes
_DB_AEROSPIKE_KEY_ATTR = "db.aerospike.key"
_DB_AEROSPIKE_GENERATION_ATTR = "db.aerospike.generation"
_DB_AEROSPIKE_TTL_ATTR = "db.aerospike.ttl"
_DB_AEROSPIKE_UDF_MODULE_ATTR = "db.aerospike.udf.module"
_DB_AEROSPIKE_UDF_FUNCTION_ATTR = "db.aerospike.udf.function"


class AerospikeInstrumentor(BaseInstrumentor):
    """OpenTelemetry Aerospike Instrumentor.

    This instrumentor wraps Aerospike client methods to automatically
    create spans for database operations.

    Note: Aerospike Python client is a C extension, so we wrap the client
    factory function (aerospike.client) to instrument each client instance.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the dependencies required for this instrumentation."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Instrument Aerospike client factory function."""
        import aerospike  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.28.0",
        )

        request_hook = kwargs.get("request_hook")
        response_hook = kwargs.get("response_hook")
        error_hook = kwargs.get("error_hook")
        capture_key = kwargs.get("capture_key", False)

        # Store original client function
        self._original_client = aerospike.client  # pylint: disable=c-extension-no-member

        # Wrap the client factory function
        wrap_function_wrapper(
            "aerospike",
            "client",
            _create_client_wrapper(
                tracer, request_hook, response_hook, error_hook, capture_key
            ),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Remove instrumentation from Aerospike client factory."""
        import aerospike  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        unwrap(aerospike, "client")


def _create_client_wrapper(
    tracer: Tracer,
    request_hook: Callable | None,
    response_hook: Callable | None,
    error_hook: Callable | None,
    capture_key: bool,
) -> Callable:
    """Create a wrapper for aerospike.client() factory function."""

    def client_wrapper(
        wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        # Create the original client
        client = wrapped(*args, **kwargs)

        # Extract config from args or kwargs
        config = None
        if args:
            config = args[0]
        elif "config" in kwargs:
            config = kwargs["config"]

        # Wrap the client instance with our instrumented proxy
        return InstrumentedAerospikeClient(
            client,
            tracer,
            request_hook,
            response_hook,
            error_hook,
            capture_key,
            config,
        )

    return client_wrapper


class InstrumentedAerospikeClient:
    """Instrumented wrapper for Aerospike Client.

    This class wraps an Aerospike client instance and adds
    OpenTelemetry tracing to all database operations.
    """

    _SINGLE_RECORD_METHODS = [
        "put",
        "get",
        "select",
        "exists",
        "remove",
        "touch",
        "operate",
        "append",
        "prepend",
        "increment",
    ]

    _BATCH_METHODS = [
        "batch_read",
        "batch_write",
        "batch_operate",
        "batch_remove",
        "batch_apply",
        # Note: get_many, exists_many, select_many were removed in aerospike 17.0.0
        # Use batch_read() instead
    ]

    _QUERY_SCAN_METHODS = ["query", "scan"]

    _UDF_METHODS = ["apply"]

    _SCAN_APPLY_METHODS = ["scan_apply"]

    _QUERY_APPLY_METHODS = ["query_apply"]

    _ADMIN_METHODS = ["truncate", "info_all"]

    def __init__(
        self,
        client: Any,
        tracer: Tracer,
        request_hook: Callable | None,
        response_hook: Callable | None,
        error_hook: Callable | None,
        capture_key: bool,
        config: dict | None = None,
    ):
        self._client = client
        self._tracer = tracer
        self._request_hook = request_hook
        self._response_hook = response_hook
        self._error_hook = error_hook
        self._capture_key = capture_key

        # Store server connection info for span attributes
        self._server_address = None
        self._server_port = None

        # Extract hosts from config if provided
        if config and isinstance(config, dict):
            hosts = config.get("hosts", [])
            if hosts:
                try:
                    first_host = hosts[0]
                    if isinstance(first_host, tuple) and len(first_host) >= 2:
                        self._server_address = str(first_host[0])
                        self._server_port = int(first_host[1])
                    elif (
                        isinstance(first_host, tuple) and len(first_host) == 1
                    ):
                        self._server_address = str(first_host[0])
                        self._server_port = 3000
                except (TypeError, AttributeError, IndexError):
                    pass

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the wrapped client.

        Wrapped methods are cached via object.__setattr__ so subsequent
        calls bypass __getattr__ entirely.
        """
        attr = getattr(self._client, name)

        # If it's a method we want to instrument, wrap and cache it
        if callable(attr):
            wrapped = None
            if name in self._SINGLE_RECORD_METHODS:
                wrapped = self._wrap_single_record_method(attr, name.upper())
            elif name in self._BATCH_METHODS:
                op_name = _get_batch_operation_name(name)
                wrapped = self._wrap_batch_method(attr, op_name)
            elif name in self._QUERY_SCAN_METHODS:
                wrapped = self._wrap_query_scan_method(attr, name.upper())
            elif name in self._UDF_METHODS:
                op_name = name.upper().replace("_", " ")
                wrapped = self._wrap_udf_method(attr, op_name)
            elif name in self._SCAN_APPLY_METHODS:
                wrapped = self._wrap_scan_apply_method(attr, "SCAN APPLY")
            elif name in self._QUERY_APPLY_METHODS:
                wrapped = self._wrap_query_apply_method(attr, "QUERY APPLY")
            elif name in self._ADMIN_METHODS:
                wrapped = self._wrap_admin_method(attr, name.upper())

            if wrapped is not None:
                object.__setattr__(self, name, wrapped)
                return wrapped

        return attr

    def connect(self, *args, **kwargs) -> InstrumentedAerospikeClient:
        """Connect to the Aerospike cluster and cache server address."""
        self._client.connect(*args, **kwargs)
        self._update_server_info_from_nodes()
        return self

    def _update_server_info_from_nodes(self) -> None:
        """Try to get actual connected server info after connection."""
        try:
            if not hasattr(self._client, "get_nodes"):
                return
            nodes = self._client.get_nodes()
            if not nodes:
                return
            node = nodes[0]
            if not hasattr(node, "name"):
                return
            # node.name is typically "host:port" or "host"
            node_name = str(node.name)
            if ":" in node_name:
                host, port = node_name.rsplit(":", 1)
                self._server_address = host
                try:
                    self._server_port = int(port)
                except ValueError:
                    self._server_port = 3000
            else:
                self._server_address = node_name
                self._server_port = 3000
        except (TypeError, AttributeError, IndexError):
            # If we can't get node info, keep the config-based values
            pass

    def close(self) -> None:
        """Close the connection."""
        self._client.close()

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._client.is_connected()

    def _set_connection_attributes(self, span: Span) -> None:
        """Set connection-related attributes on span."""
        # Use cached server address if available
        if self._server_address:
            span.set_attribute(_SERVER_ADDRESS_ATTR, self._server_address)
            if self._server_port:
                span.set_attribute(_SERVER_PORT_ATTR, self._server_port)

    def _wrap_single_record_method(
        self, method: Callable, operation: str
    ) -> Callable:
        """Wrap a single record operation method."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            key_tuple = args[0] if args else None
            namespace, set_name = _extract_namespace_set_from_key(key_tuple)

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                    # Optional: capture key
                    if self._capture_key and key_tuple and len(key_tuple) > 2:
                        user_key = key_tuple[2]  # pylint: disable=unsubscriptable-object
                        if user_key is not None:
                            span.set_attribute(
                                _DB_AEROSPIKE_KEY_ATTR, str(user_key)
                            )

                # Request hook
                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    # Response hook
                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    # Set generation/TTL from result
                    if span.is_recording():
                        _set_result_attributes(span, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _wrap_batch_method(self, method: Callable, operation: str) -> Callable:
        """Wrap a batch operation method."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            keys = args[0] if args else None
            namespace, set_name = _extract_namespace_set_from_batch(keys)

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                    # Batch size
                    if keys and isinstance(keys, (list, tuple)):
                        span.set_attribute(
                            _DB_OPERATION_BATCH_SIZE_ATTR, len(keys)
                        )

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _wrap_query_scan_method(
        self, method: Callable, operation: str
    ) -> Callable:
        """Wrap a query/scan operation method."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            namespace = args[0] if args else None
            set_name = args[1] if len(args) > 1 else None

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _wrap_udf_method(self, method: Callable, operation: str) -> Callable:
        """Wrap a UDF operation method."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            key_tuple = args[0] if args else None
            namespace, set_name = _extract_namespace_set_from_key(key_tuple)

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    self._set_udf_span_attributes(
                        span, operation, namespace, set_name, args, key_tuple
                    )

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _wrap_scan_apply_method(
        self, method: Callable, operation: str
    ) -> Callable:
        """Wrap scan_apply: scan_apply(namespace, set, module, function, args)."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            namespace = args[0] if args else None
            set_name = args[1] if len(args) > 1 else None

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                    # UDF info: scan_apply(ns, set, module, function, args)
                    if len(args) > 2:
                        span.set_attribute(
                            _DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[2])
                        )
                    if len(args) > 3:
                        span.set_attribute(
                            _DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[3])
                        )

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _wrap_query_apply_method(
        self, method: Callable, operation: str
    ) -> Callable:
        """Wrap query_apply: query_apply(namespace, set, predicate, module, function, args)."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            namespace = args[0] if args else None
            set_name = args[1] if len(args) > 1 else None

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                    # UDF info: query_apply(ns, set, predicate, module, function, args)
                    if len(args) > 3:
                        span.set_attribute(
                            _DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[3])
                        )
                    if len(args) > 4:
                        span.set_attribute(
                            _DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[4])
                        )

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper

    def _set_udf_span_attributes(
        self,
        span: Span,
        operation: str,
        namespace: str | None,
        set_name: str | None,
        args: tuple,
        key_tuple: tuple | None,
    ) -> None:
        """Set span attributes for UDF operations."""
        span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

        if namespace:
            span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
        if set_name:
            span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

        span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
        self._set_connection_attributes(span)

        # UDF info
        if len(args) > 1:
            span.set_attribute(_DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[1]))
        if len(args) > 2:
            span.set_attribute(_DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[2]))

        # Optional: capture key
        if self._capture_key and key_tuple and len(key_tuple) > 2:
            user_key = key_tuple[2]  # pylint: disable=unsubscriptable-object
            if user_key is not None:
                span.set_attribute(_DB_AEROSPIKE_KEY_ATTR, str(user_key))

    def _wrap_admin_method(self, method: Callable, operation: str) -> Callable:
        """Wrap an admin operation method."""

        @functools.wraps(method)
        def wrapper(*args, **kwargs) -> Any:
            if not is_instrumentation_enabled():
                return method(*args, **kwargs)

            namespace = args[0] if args and isinstance(args[0], str) else None
            set_name = (
                args[1] if len(args) > 1 and isinstance(args[1], str) else None
            )

            span_name = _generate_span_name(operation, namespace, set_name)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
            ) as span:
                if span.is_recording():
                    span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)

                    if namespace:
                        span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                    if set_name:
                        span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)

                    span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                    self._set_connection_attributes(span)

                if self._request_hook:
                    self._request_hook(span, operation, args, kwargs)

                try:
                    result = method(*args, **kwargs)

                    if self._response_hook:
                        self._response_hook(span, operation, result)

                    return result

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if span.is_recording():
                        _set_error_attributes(span, exc)

                    if self._error_hook:
                        self._error_hook(span, operation, exc)

                    raise

        return wrapper


# Helper functions


def _get_batch_operation_name(method: str) -> str:
    """Convert batch method name to operation name."""
    method_upper = method.upper()
    if method_upper.startswith("BATCH_"):
        return f"BATCH {method_upper[6:]}"
    return f"BATCH {method_upper}"


def _extract_namespace_set_from_key(
    key_tuple: tuple | None,
) -> tuple[str | None, str | None]:
    """Extract namespace and set from a single key tuple.

    Key format: (namespace, set, key[, digest])
    """
    if not key_tuple or not isinstance(key_tuple, tuple):
        return None, None

    namespace = key_tuple[0] if len(key_tuple) > 0 else None
    set_name = key_tuple[1] if len(key_tuple) > 1 else None
    return namespace, set_name


def _extract_namespace_set_from_batch(
    keys: list | tuple | None,
) -> tuple[str | None, str | None]:
    """Extract namespace and set from batch keys (uses first key)."""
    if not keys or not isinstance(keys, (list, tuple)):
        return None, None

    first_key = keys[0]
    if isinstance(first_key, tuple) and len(first_key) >= 2:
        return first_key[0], first_key[1]
    return None, None


def _generate_span_name(
    operation: str, namespace: str | None, set_name: str | None
) -> str:
    """Generate span name following convention: {operation} {namespace}.{set}."""
    if namespace and set_name:
        return f"{operation} {namespace}.{set_name}"
    if namespace:
        return f"{operation} {namespace}"
    return operation


def _set_result_attributes(span: Span, result: Any) -> None:
    """Set attributes from operation result."""
    if isinstance(result, tuple) and len(result) >= 2:
        # Format: (key, meta, bins) or (key, meta)
        meta = result[1] if len(result) > 1 else None
        if isinstance(meta, dict):
            if "gen" in meta:
                span.set_attribute(_DB_AEROSPIKE_GENERATION_ATTR, meta["gen"])
            if "ttl" in meta:
                span.set_attribute(_DB_AEROSPIKE_TTL_ATTR, meta["ttl"])


def _set_error_attributes(span: Span, exc: Exception) -> None:
    """Set error attributes on span."""
    span.set_status(Status(StatusCode.ERROR, str(exc)))
    span.set_attribute(_ERROR_TYPE_ATTR, type(exc).__name__)

    # Aerospike specific error code
    if hasattr(exc, "code"):
        span.set_attribute(_DB_RESPONSE_STATUS_CODE_ATTR, str(exc.code))


# Public API
__all__ = [
    "AerospikeInstrumentor",
    "InstrumentedAerospikeClient",
    "__version__",
]
