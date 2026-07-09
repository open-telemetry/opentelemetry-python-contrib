# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Weaviate client instrumentation supporting `weaviate-client`_, it can be
enabled by using ``WeaviateInstrumentor``.

.. _weaviate-client: https://pypi.org/project/weaviate-client/

Usage
-----

.. code:: python

    import weaviate
    from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor

    WeaviateInstrumentor().instrument()

    client = weaviate.connect_to_local()
    client.collections.create("Article")
    client.collections.exists("Article")
    client.collections.delete("Article")

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the
``weaviate`` value for ``db.system.name``. Only the ``weaviate-client`` v4
collection-management operations are instrumented; per-collection data and
query operations on a live connection are out of scope because there is no
stable vector semantic convention for them and they require a running server.
Vector-database-specific fields (such as the number of objects, ``limit`` /
``top_k``, query vectors, or filters) are not emitted for the same reason.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.weaviate._wrap import _wrap
from opentelemetry.instrumentation.weaviate.package import _instruments
from opentelemetry.instrumentation.weaviate.version import __version__
from opentelemetry.trace import Tracer, get_tracer

_MODULE = "weaviate.collections.collections"
_COLLECTIONS_CLASS = "_Collections"

# Collection-management methods on ``weaviate.collections.collections._Collections``
# (weaviate-client v4). Not every method is guaranteed to exist on every
# supported release, so instrumentation only wraps the methods actually present
# on the installed class.
_COLLECTIONS_METHODS: tuple[str, ...] = (
    "create",
    "get",
    "delete",
    "delete_all",
    "create_from_dict",
    "exists",
    "list_all",
)


class WeaviateInstrumentor(BaseInstrumentor):
    """An instrumentor for Weaviate's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        from weaviate.collections.collections import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            _Collections,
        )

        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        for method in _COLLECTIONS_METHODS:
            if hasattr(_Collections, method):
                wrap_function_wrapper(
                    _MODULE,
                    f"{_COLLECTIONS_CLASS}.{method}",
                    _wrap(tracer, method),
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        from weaviate.collections.collections import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            _Collections,
        )

        for method in _COLLECTIONS_METHODS:
            if hasattr(_Collections, method):
                unwrap(_Collections, method)
