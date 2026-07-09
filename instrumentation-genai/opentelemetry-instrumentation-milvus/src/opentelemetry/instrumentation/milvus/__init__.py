# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Milvus client instrumentation supporting `pymilvus`, it can be enabled by
using ``MilvusInstrumentor``.

.. _pymilvus: https://pypi.org/project/pymilvus/

Usage
-----

.. code:: python

    from pymilvus import MilvusClient
    from opentelemetry.instrumentation.milvus import MilvusInstrumentor

    MilvusInstrumentor().instrument()

    client = MilvusClient("milvus_demo.db")
    client.create_collection("my_collection", dimension=4)
    client.insert(
        "my_collection",
        data=[{"id": 1, "vector": [0.1, 0.2, 0.3, 0.4]}],
    )
    client.search("my_collection", data=[[0.1, 0.2, 0.3, 0.4]], limit=1)

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the ``milvus``
value for ``db.system.name``. Vector-database-specific fields (such as the
number of vectors, ``limit`` / ``top_k``, query vectors, or filters) are not
emitted because there is currently no stable semantic convention for them.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.milvus._wrap import _wrap
from opentelemetry.instrumentation.milvus.package import _instruments
from opentelemetry.instrumentation.milvus.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer, get_tracer

_MODULE = "pymilvus"
_CLIENT_CLASS = "MilvusClient"

# Methods on ``pymilvus.MilvusClient`` that carry a ``collection_name`` as their
# first argument. Not every method necessarily exists on every supported
# ``pymilvus`` version, so instrumentation only wraps the methods actually
# present on the installed client class.
_CLIENT_METHODS: tuple[str, ...] = (
    "create_collection",
    "insert",
    "upsert",
    "delete",
    "search",
    "get",
    "query",
    "hybrid_search",
)


class MilvusInstrumentor(BaseInstrumentor):
    """An instrumentor for Milvus's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        import pymilvus  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        client = getattr(pymilvus, _CLIENT_CLASS, None)
        for method in _CLIENT_METHODS:
            if client is not None and hasattr(client, method):
                wrap_function_wrapper(
                    _MODULE,
                    f"{_CLIENT_CLASS}.{method}",
                    _wrap(tracer, method),
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        import pymilvus  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        client = getattr(pymilvus, _CLIENT_CLASS, None)
        for method in _CLIENT_METHODS:
            if client is not None and hasattr(client, method):
                unwrap(client, method)
