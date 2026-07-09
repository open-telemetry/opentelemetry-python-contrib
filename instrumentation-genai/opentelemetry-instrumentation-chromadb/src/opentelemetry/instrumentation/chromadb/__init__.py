# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
ChromaDB client instrumentation supporting `chromadb`, it can be enabled by
using ``ChromaInstrumentor``.

.. _chromadb: https://pypi.org/project/chromadb/

Usage
-----

.. code:: python

    import chromadb
    from opentelemetry.instrumentation.chromadb import ChromaInstrumentor

    ChromaInstrumentor().instrument()

    client = chromadb.Client()
    collection = client.create_collection("my_collection")
    collection.add(ids=["id1"], documents=["hello world"])
    collection.query(query_texts=["hello"], n_results=1)

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the ``chromadb``
value for ``db.system.name``. Vector-database-specific fields (such as the number
of embeddings, ``top_k`` / ``n_results``, ids, or ``where`` filters) are not
emitted because there is currently no stable semantic convention for them.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.chromadb._wrap import (
    _collection_name_from_create_args,
    _wrap,
)
from opentelemetry.instrumentation.chromadb.package import _instruments
from opentelemetry.instrumentation.chromadb.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer, get_tracer

_COLLECTION_MODULE = "chromadb.api.models.Collection"
_COLLECTION_CLASS = "Collection"

# Methods on ``chromadb.api.models.Collection.Collection``. The collection name
# is read from the wrapped instance's ``name`` attribute.
_COLLECTION_METHODS: tuple[str, ...] = (
    "add",
    "get",
    "query",
    "delete",
    "update",
    "upsert",
    "peek",
    "count",
    "modify",
)

_CLIENT_MODULE = "chromadb.api.client"
_CLIENT_CLASS = "Client"

# Methods on ``chromadb.api.client.Client``. The collection name is read from
# the call arguments.
_CLIENT_METHODS: tuple[str, ...] = (
    "create_collection",
    "get_or_create_collection",
    "delete_collection",
)


class ChromaInstrumentor(BaseInstrumentor):
    """An instrumentor for ChromaDB's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        for method in _COLLECTION_METHODS:
            wrap_function_wrapper(
                _COLLECTION_MODULE,
                f"{_COLLECTION_CLASS}.{method}",
                _wrap(tracer, method),
            )

        for method in _CLIENT_METHODS:
            wrap_function_wrapper(
                _CLIENT_MODULE,
                f"{_CLIENT_CLASS}.{method}",
                _wrap(
                    tracer,
                    method,
                    collection_name_from_args=_collection_name_from_create_args,
                ),
            )

    def _uninstrument(self, **kwargs: Any) -> None:
        import chromadb.api.client  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
        import chromadb.api.models.Collection  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        for method in _COLLECTION_METHODS:
            unwrap(chromadb.api.models.Collection.Collection, method)

        for method in _CLIENT_METHODS:
            unwrap(chromadb.api.client.Client, method)
