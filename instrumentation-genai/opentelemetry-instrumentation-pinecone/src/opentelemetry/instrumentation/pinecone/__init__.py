# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument the `pinecone`_ vector database client with OpenTelemetry.

.. _pinecone: https://pypi.org/project/pinecone

This instrumentation emits **generic OpenTelemetry database spans** (``db.*``
semantic conventions) for the Pinecone data-plane ``Index`` operations. It does
*not* emit any vector-specific telemetry (such as ``top_k``, query vectors, or
match scores) because there is currently no stable OpenTelemetry semantic
convention for those fields.

Each instrumented call produces a single ``CLIENT`` span carrying:

* ``db.system.name`` — always the literal ``"pinecone"``.
* ``db.operation.name`` — the invoked method
  (``query``/``upsert``/``delete``/``fetch``/``update``/``describe_index_stats``).
* ``db.collection.name`` — the Pinecone index name, when it can be derived
  from the client host.
* ``db.namespace`` — the Pinecone namespace, when supplied to the call.

On failure the span records the exception, sets an error status, adds
``error.type`` and re-raises the original exception unmodified.

Usage
-----

.. code:: python

    from pinecone import Pinecone
    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor

    PineconeInstrumentor().instrument()

    pc = Pinecone(api_key="...")
    index = pc.Index(host="https://my-index-abc.svc.pinecone.io")
    index.query(vector=[0.1, 0.2, 0.3], top_k=3, namespace="ns")

.. note::
    Instrument **before** creating ``Index`` clients. The Pinecone SDK binds
    some data-plane methods per-instance at construction time, so clients
    created prior to instrumentation may not be fully traced.

API
---
"""

from __future__ import annotations

import importlib.util
from logging import getLogger
from typing import Any, Callable, Collection
from urllib.parse import urlparse

from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pinecone.package import _instruments
from opentelemetry.instrumentation.pinecone.version import __version__
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    unwrap,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, Tracer, get_tracer
from opentelemetry.trace.status import Status, StatusCode

_LOG = getLogger(__name__)

# Pinecone has no dedicated ``db.system.name`` well-known value, so the literal
# ``"pinecone"`` is used per the OpenTelemetry database semantic conventions.
_DB_SYSTEM_PINECONE = "pinecone"

# Data-plane ``Index`` methods to instrument. These are defined on the Pinecone
# ``Index`` class (exposed as ``pinecone.Index``).
_WRAPPED_METHODS: tuple[str, ...] = (
    "query",
    "upsert",
    "delete",
    "fetch",
    "update",
    "describe_index_stats",
)

_INDEX_CLASS = "Index"

# The module that defines the ``Index`` class has moved between Pinecone
# releases (``pinecone.index`` on v9, ``pinecone.data.index`` on v5), so the
# candidates are probed in order and the first importable one is used.
_INDEX_MODULE_CANDIDATES: tuple[str, ...] = (
    "pinecone.index",
    "pinecone.data.index",
)


def _index_module() -> str | None:
    """Return the importable module that defines the Pinecone ``Index`` class."""
    for module in _INDEX_MODULE_CANDIDATES:
        if importlib.util.find_spec(module) is not None:
            return module
    return None


def _index_host(instance: Any) -> str | None:
    """Return the client host for an ``Index`` instance across SDK versions.

    Pinecone v9 stores it on ``instance._host``; v5 exposes it via
    ``instance._config.host``.
    """
    host = getattr(instance, "_host", None)
    if isinstance(host, str) and host:
        return host
    config = getattr(instance, "_config", None)
    config_host = getattr(config, "host", None)
    if isinstance(config_host, str) and config_host:
        return config_host
    return None


def _index_name(instance: Any) -> str | None:
    """Best-effort extraction of the Pinecone index name from a client host.

    Pinecone data-plane hosts look like ``my-index-abc123.svc.<region>.pinecone.io``.
    The index name is the label preceding ``.svc``. Returns ``None`` when the
    host is unavailable or cannot be parsed.
    """
    host = _index_host(instance)
    if not host:
        return None
    hostname = urlparse(host).hostname if "://" in host else host
    if not hostname:
        return None
    hostname = hostname.split(":", 1)[0]
    # The index name is the leading label of the host, e.g. the ``my-index``
    # in ``my-index.svc.<region>.pinecone.io``.
    label = hostname.partition(".")[0]
    return label or None


def _wrap_index_method(
    tracer: Tracer, operation: str
) -> Callable[[Any, Any, tuple[Any, ...], dict[str, Any]], Any]:
    def wrapper(
        wrapped: Any,
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        namespace = kwargs.get("namespace") or None
        collection = _index_name(instance)
        target = collection or namespace
        span_name = f"{operation} {target}" if target else operation

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if span.is_recording():
                # Literal "pinecone": no well-known db.system.name value exists.
                span.set_attribute(DB_SYSTEM_NAME, _DB_SYSTEM_PINECONE)
                span.set_attribute(DB_OPERATION_NAME, operation)
                if collection is not None:
                    span.set_attribute(DB_COLLECTION_NAME, collection)
                if namespace is not None:
                    span.set_attribute(DB_NAMESPACE, namespace)

            try:
                return wrapped(*args, **kwargs)
            except Exception as exc:
                if span.is_recording():
                    span.set_attribute(ERROR_TYPE, type(exc).__qualname__)
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    return wrapper


class PineconeInstrumentor(BaseInstrumentor):
    """An instrumentor for the Pinecone client library.

    Emits generic OpenTelemetry database (``db.*``) spans for the Pinecone
    data-plane ``Index`` operations.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )
        module = _index_module()
        if module is None:
            _LOG.debug(
                "Could not locate the Pinecone Index module; "
                "instrumentation is a no-op."
            )
            return
        for method in _WRAPPED_METHODS:
            wrap_function_wrapper(
                module,
                f"{_INDEX_CLASS}.{method}",
                _wrap_index_method(tracer, method),
            )

    def _uninstrument(self, **kwargs: Any) -> None:
        module = _index_module()
        if module is None:
            return
        for method in _WRAPPED_METHODS:
            unwrap(f"{module}.{_INDEX_CLASS}", method)
