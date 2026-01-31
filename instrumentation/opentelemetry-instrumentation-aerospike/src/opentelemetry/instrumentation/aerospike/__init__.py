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
_DB_SYSTEM_ATTR = "db.system.name"
_DB_NAMESPACE_ATTR = "db.namespace"
_DB_COLLECTION_NAME_ATTR = "db.collection.name"
_DB_OPERATION_NAME_ATTR = "db.operation.name"
_DB_OPERATION_BATCH_SIZE_ATTR = "db.operation.batch.size"
_DB_RESPONSE_STATUS_CODE_ATTR = "db.response.status_code"
_SERVER_ADDRESS_ATTR = "server.address"
_SERVER_PORT_ATTR = "server.port"
_DB_USER_ATTR = "db.user"
_ERROR_TYPE_ATTR = "error.type"

# Aerospike-specific attributes
_DB_AEROSPIKE_KEY_ATTR = "db.aerospike.key"
_DB_AEROSPIKE_GENERATION_ATTR = "db.aerospike.generation"
_DB_AEROSPIKE_TTL_ATTR = "db.aerospike.ttl"
_DB_AEROSPIKE_UDF_MODULE_ATTR = "db.aerospike.udf.module"
_DB_AEROSPIKE_UDF_FUNCTION_ATTR = "db.aerospike.udf.function"
_DB_AEROSPIKE_BINS_ATTR = "db.aerospike.bins"


class AerospikeInstrumentor(BaseInstrumentor):
    """OpenTelemetry Aerospike Instrumentor."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.28.0",
        )

        wrap_function_wrapper(
            "aerospike",
            "client",
            _create_client_wrapper(
                tracer,
                kwargs.get("request_hook"),
                kwargs.get("response_hook"),
                kwargs.get("error_hook"),
                kwargs.get("capture_key", False),
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
    def client_wrapper(
        wrapped: Callable, instance: Any, args: tuple, kwargs: dict
    ) -> Any:
        client = wrapped(*args, **kwargs)
        config = args[0] if args else kwargs.get("config")
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


def _traced_method(
    tracer: Tracer,
    method: Callable,
    operation: str,
    extract_ns_set: Callable[[tuple], tuple[str | None, str | None]],
    client_instance: InstrumentedAerospikeClient,
    set_extra_attrs: Callable[[Span, tuple], None] | None = None,
    set_result_attrs: Callable[[Span, Any], None] | None = None,
) -> Callable:
    """Generic wrapper for tracing Aerospike methods."""

    @functools.wraps(method)
    def wrapper(*args, **kwargs) -> Any:
        if not is_instrumentation_enabled():
            return method(*args, **kwargs)

        namespace, set_name = extract_ns_set(args)
        span_name = _generate_span_name(operation, namespace, set_name)

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(_DB_SYSTEM_ATTR, _DB_SYSTEM)
                if namespace:
                    span.set_attribute(_DB_NAMESPACE_ATTR, namespace)
                if set_name:
                    span.set_attribute(_DB_COLLECTION_NAME_ATTR, set_name)
                span.set_attribute(_DB_OPERATION_NAME_ATTR, operation)
                client_instance._set_connection_attributes(span)  # noqa: SLF001

                if set_extra_attrs:
                    set_extra_attrs(span, args)

            if client_instance._request_hook:  # noqa: SLF001
                client_instance._request_hook(  # noqa: SLF001
                    span, operation, args, kwargs
                )

            try:
                result = method(*args, **kwargs)
                if client_instance._response_hook:  # noqa: SLF001
                    client_instance._response_hook(  # noqa: SLF001
                        span, operation, result
                    )
                if set_result_attrs and span.is_recording():
                    set_result_attrs(span, result)
                return result
            except Exception as exc:
                if span.is_recording():
                    _set_error_attributes(span, exc)
                if client_instance._error_hook:  # noqa: SLF001
                    client_instance._error_hook(span, operation, exc)  # noqa: SLF001
                raise

    return wrapper


class InstrumentedAerospikeClient:
    """Instrumented wrapper for Aerospike Client."""

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
        self._server_address = None
        self._server_port = None
        self._user = None

        if config and isinstance(config, dict):
            hosts = config.get("hosts", [])
            if hosts:
                try:
                    host = hosts[0]
                    if isinstance(host, tuple):
                        self._server_address = str(host[0])
                        self._server_port = (
                            int(host[1]) if len(host) > 1 else 3000
                        )
                except (TypeError, AttributeError, IndexError):
                    pass

            if "user" in config:
                self._user = str(config["user"])
            elif "username" in config:
                self._user = str(config["username"])

        # Configuration for method instrumentation:
        # method_name: (operation_name, extractor_func, extra_attrs_func, result_attrs_func)
        self._method_config = {}
        self._init_method_config()

    def _init_method_config(self):
        # Single record operations
        for method in [
            "get",
            "exists",
            "remove",
            "touch",
            "operate",
            "append",
            "prepend",
            "increment",
        ]:
            self._method_config[method] = (
                method.upper(),
                _ns_set_from_key_arg,
                self._extra_attrs_capture_key,
                _set_result_attributes if method == "get" else None,
            )

        # Operations with bins
        for method in ["put", "select"]:
            self._method_config[method] = (
                method.upper(),
                _ns_set_from_key_arg,
                self._extra_attrs_bins,
                None,
            )

        # Batch operations
        for method in [
            "batch_read",
            "batch_write",
            "batch_operate",
            "batch_remove",
            "batch_apply",
        ]:
            self._method_config[method] = (
                _get_batch_operation_name(method),
                _ns_set_from_batch_arg,
                _extra_attrs_batch_size,
                None,
            )

        # UDF operations
        self._method_config["apply"] = (
            "APPLY",
            _ns_set_from_key_arg,
            self._extra_attrs_udf_apply,
            None,
        )
        self._method_config["scan_apply"] = (
            "SCAN APPLY",
            _ns_set_from_positional_args,
            _extra_attrs_scan_apply_udf,
            None,
        )
        self._method_config["query_apply"] = (
            "QUERY APPLY",
            _ns_set_from_positional_args,
            _extra_attrs_query_apply_udf,
            None,
        )

        # Admin/Info operations
        self._method_config["truncate"] = (
            "TRUNCATE",
            _ns_set_from_admin_args,
            None,
            None,
        )
        self._method_config["info_all"] = (
            "INFO_ALL",
            _ns_set_noop,
            None,
            None,
        )

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        if name in self._method_config:
            op_name, extractor, extra_attrs, res_attrs = self._method_config[
                name
            ]
            wrapped = _traced_method(
                self._tracer,
                attr,
                op_name,
                extractor,
                self,
                extra_attrs,
                res_attrs,
            )
            object.__setattr__(self, name, wrapped)
            return wrapped

        if name in ("query", "scan"):
            return self._create_query_scan_factory(attr, name.upper())

        return attr

    def connect(self, *args, **kwargs) -> InstrumentedAerospikeClient:
        self._client.connect(*args, **kwargs)
        self._update_server_info_from_nodes()
        return self

    def _update_server_info_from_nodes(self) -> None:
        try:
            if not hasattr(self._client, "get_nodes"):
                return
            nodes = self._client.get_nodes()
            if not nodes:
                return
            node = nodes[0]
            if isinstance(node, tuple) and len(node) >= 2:
                self._server_address = str(node[0])
                self._server_port = int(node[1])
            elif hasattr(node, "name"):
                host, port = _parse_host_port(str(node.name))
                if host:
                    self._server_address = host
                    self._server_port = port or 3000
        except (TypeError, AttributeError, IndexError, ValueError):
            pass

    def close(self) -> None:
        self._client.close()

    def is_connected(self) -> bool:
        return self._client.is_connected()

    def _set_connection_attributes(self, span: Span) -> None:
        if self._server_address:
            span.set_attribute(_SERVER_ADDRESS_ATTR, self._server_address)
            if self._server_port:
                span.set_attribute(_SERVER_PORT_ATTR, self._server_port)
        if self._user:
            span.set_attribute(_DB_USER_ATTR, self._user)

    def _create_query_scan_factory(
        self, method: Callable, operation: str
    ) -> Callable:
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            query_scan_obj = method(*args, **kwargs)
            namespace, set_name = _ns_set_from_positional_args(args)
            return InstrumentedQueryScan(
                query_scan_obj, operation, namespace, set_name, self
            )

        return wrapper

    def _extra_attrs_capture_key(self, span: Span, args: tuple) -> None:
        if not self._capture_key:
            return
        key_tuple = args[0] if args else None
        if (
            key_tuple
            and isinstance(key_tuple, tuple)
            and len(key_tuple) > 2
            and key_tuple[2] is not None
        ):
            span.set_attribute(_DB_AEROSPIKE_KEY_ATTR, str(key_tuple[2]))

    def _extra_attrs_bins(self, span: Span, args: tuple) -> None:
        self._extra_attrs_capture_key(span, args)
        if len(args) > 1:
            bins = args[1]
            if isinstance(bins, dict):
                span.set_attribute(_DB_AEROSPIKE_BINS_ATTR, list(bins.keys()))
            elif isinstance(bins, (list, tuple)):
                span.set_attribute(_DB_AEROSPIKE_BINS_ATTR, list(bins))

    def _extra_attrs_udf_apply(self, span: Span, args: tuple) -> None:
        if len(args) > 1:
            span.set_attribute(_DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[1]))
        if len(args) > 2:
            span.set_attribute(_DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[2]))
        self._extra_attrs_capture_key(span, args)


class InstrumentedQueryScan:
    """Instrumented wrapper for Aerospike Query/Scan objects."""

    _EXECUTION_METHODS = frozenset(
        {"results", "foreach", "execute_background"}
    )

    def __init__(
        self,
        query_scan_obj: Any,
        operation: str,
        namespace: str | None,
        set_name: str | None,
        client: InstrumentedAerospikeClient,
    ):
        self._inner = query_scan_obj
        self._operation = operation
        self._namespace = namespace
        self._set_name = set_name
        self._client = client

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        if name in self._EXECUTION_METHODS:
            wrapped = _traced_method(
                self._client._tracer,  # noqa: SLF001
                attr,
                self._operation,
                lambda args: (self._namespace, self._set_name),
                self._client,
            )
            object.__setattr__(self, name, wrapped)
            return wrapped

        # Chaining support for config methods
        @functools.wraps(attr)
        def chaining_wrapper(*args, **kwargs):
            result = attr(*args, **kwargs)
            return self if result is self._inner else result

        return chaining_wrapper


# -- Helper Functions --


def _ns_set_from_key_arg(args: tuple) -> tuple[str | None, str | None]:
    key_tuple = args[0] if args and isinstance(args[0], tuple) else None
    if not key_tuple:
        return None, None
    return key_tuple[0], key_tuple[1] if len(key_tuple) > 1 else None


def _ns_set_from_batch_arg(args: tuple) -> tuple[str | None, str | None]:
    keys = args[0] if args and isinstance(args[0], (list, tuple)) else None
    if not keys:
        return None, None
    first_key = keys[0]
    if isinstance(first_key, tuple) and len(first_key) >= 2:
        return first_key[0], first_key[1]
    return None, None


def _ns_set_from_positional_args(
    args: tuple,
) -> tuple[str | None, str | None]:
    namespace = args[0] if args else None
    set_name = args[1] if len(args) > 1 else None
    return namespace, set_name


def _ns_set_from_admin_args(args: tuple) -> tuple[str | None, str | None]:
    namespace = args[0] if args and isinstance(args[0], str) else None
    set_name = args[1] if len(args) > 1 and isinstance(args[1], str) else None
    return namespace, set_name


def _ns_set_noop(args: tuple) -> tuple[str | None, str | None]:
    return None, None


def _extra_attrs_batch_size(span: Span, args: tuple) -> None:
    keys = args[0] if args and isinstance(args[0], (list, tuple)) else None
    if keys:
        span.set_attribute(_DB_OPERATION_BATCH_SIZE_ATTR, len(keys))


def _extra_attrs_scan_apply_udf(span: Span, args: tuple) -> None:
    if len(args) > 2:
        span.set_attribute(_DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[2]))
    if len(args) > 3:
        span.set_attribute(_DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[3]))


def _extra_attrs_query_apply_udf(span: Span, args: tuple) -> None:
    if len(args) > 3:
        span.set_attribute(_DB_AEROSPIKE_UDF_MODULE_ATTR, str(args[3]))
    if len(args) > 4:
        span.set_attribute(_DB_AEROSPIKE_UDF_FUNCTION_ATTR, str(args[4]))


def _get_batch_operation_name(method: str) -> str:
    method_upper = method.upper()
    if method_upper.startswith("BATCH_"):
        return f"BATCH {method_upper[6:]}"
    return f"BATCH {method_upper}"


def _parse_host_port(address: str) -> tuple[str | None, int | None]:
    if not address:
        return None, None
    host, port = address, None
    if address.startswith("["):
        bracket_end = address.find("]")
        if bracket_end >= 0:
            host = address[1:bracket_end]
            rest = address[bracket_end + 1 :]
            if rest.startswith(":"):
                try:
                    port = int(rest[1:])
                except ValueError:
                    pass
    elif address.count(":") == 1:
        host, port_str = address.split(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            pass
    return host, port


def _generate_span_name(
    operation: str, namespace: str | None, set_name: str | None
) -> str:
    if namespace and set_name:
        return f"{operation} {namespace}.{set_name}"
    if namespace:
        return f"{operation} {namespace}"
    return operation


def _set_result_attributes(span: Span, result: Any) -> None:
    if isinstance(result, tuple) and len(result) >= 2:
        meta = result[1]
        if isinstance(meta, dict):
            if "gen" in meta:
                span.set_attribute(_DB_AEROSPIKE_GENERATION_ATTR, meta["gen"])
            if "ttl" in meta:
                span.set_attribute(_DB_AEROSPIKE_TTL_ATTR, meta["ttl"])


def _set_error_attributes(span: Span, exc: Exception) -> None:
    span.set_status(Status(StatusCode.ERROR, str(exc)))
    span.set_attribute(_ERROR_TYPE_ATTR, type(exc).__name__)
    if hasattr(exc, "code"):
        span.set_attribute(_DB_RESPONSE_STATUS_CODE_ATTR, str(exc.code))


# Public API
__all__ = [
    "AerospikeInstrumentor",
    "InstrumentedAerospikeClient",
    "InstrumentedQueryScan",
    "__version__",
]
