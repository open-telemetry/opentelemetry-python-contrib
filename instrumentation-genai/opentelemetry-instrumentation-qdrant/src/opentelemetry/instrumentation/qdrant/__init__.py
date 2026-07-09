# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Qdrant client instrumentation supporting `qdrant-client`, it can be enabled by
using ``QdrantInstrumentor``.

.. _qdrant-client: https://pypi.org/project/qdrant-client/

Usage
-----

.. code:: python

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    from opentelemetry.instrumentation.qdrant import QdrantInstrumentor

    QdrantInstrumentor().instrument()

    client = QdrantClient(":memory:")
    client.create_collection(
        "my_collection",
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    client.upsert(
        "my_collection",
        points=[PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4])],
    )
    client.query_points("my_collection", query=[0.1, 0.2, 0.3, 0.4], limit=1)

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the ``qdrant``
value for ``db.system.name``. Vector-database-specific fields (such as the
number of vectors, ``limit`` / ``top_k``, query vectors, or filters) are not
emitted because there is currently no stable semantic convention for them.

API
---
"""

from __future__ import annotations

import inspect
from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.qdrant._wrap import _wrap, _wrap_async
from opentelemetry.instrumentation.qdrant.package import _instruments
from opentelemetry.instrumentation.qdrant.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer, get_tracer

_MODULE = "qdrant_client"
_SYNC_CLIENT_CLASS = "QdrantClient"
_ASYNC_CLIENT_CLASS = "AsyncQdrantClient"

# Methods on ``qdrant_client.QdrantClient`` / ``AsyncQdrantClient`` that carry a
# ``collection_name`` as their first argument. Not every method exists on every
# supported ``qdrant-client`` version (for example ``search`` and
# ``search_batch`` were removed in newer releases in favor of ``query_points``),
# so instrumentation only wraps the methods actually present on the installed
# client class.
_CLIENT_METHODS: tuple[str, ...] = (
    "upsert",
    "search",
    "search_batch",
    "query_points",
    "query_batch_points",
    "retrieve",
    "delete",
    "create_collection",
    "get_collection",
    "delete_collection",
    "upload_points",
    "upload_collection",
    "scroll",
    "update_vectors",
    "set_payload",
)


class QdrantInstrumentor(BaseInstrumentor):
    """An instrumentor for Qdrant's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        import qdrant_client  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        sync_client = getattr(qdrant_client, _SYNC_CLIENT_CLASS, None)
        for method in _CLIENT_METHODS:
            if sync_client is not None and hasattr(sync_client, method):
                wrap_function_wrapper(
                    _MODULE,
                    f"{_SYNC_CLIENT_CLASS}.{method}",
                    _wrap(tracer, method),
                )

        async_client = getattr(qdrant_client, _ASYNC_CLIENT_CLASS, None)
        for method in _CLIENT_METHODS:
            if async_client is not None and hasattr(async_client, method):
                # A few methods (``upload_points``/``upload_collection``) are
                # synchronous even on ``AsyncQdrantClient``, so they must use the
                # sync wrapper; wrapping them with the async wrapper would turn
                # them into coroutine functions that never run (or raise on
                # ``await``).
                if inspect.iscoroutinefunction(getattr(async_client, method)):
                    wrapper = _wrap_async(tracer, method)
                else:
                    wrapper = _wrap(tracer, method)
                wrap_function_wrapper(
                    _MODULE,
                    f"{_ASYNC_CLIENT_CLASS}.{method}",
                    wrapper,
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        import qdrant_client  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        sync_client = getattr(qdrant_client, _SYNC_CLIENT_CLASS, None)
        async_client = getattr(qdrant_client, _ASYNC_CLIENT_CLASS, None)
        for method in _CLIENT_METHODS:
            if sync_client is not None and hasattr(sync_client, method):
                unwrap(sync_client, method)
            if async_client is not None and hasattr(async_client, method):
                unwrap(async_client, method)
