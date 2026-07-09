# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Marqo client instrumentation supporting `marqo`, it can be enabled by
using ``MarqoInstrumentor``.

.. _marqo: https://pypi.org/project/marqo/

Usage
-----

.. code:: python

    import marqo
    from opentelemetry.instrumentation.marqo import MarqoInstrumentor

    MarqoInstrumentor().instrument()

    client = marqo.Client(url="http://localhost:8882")
    client.create_index("my-index")
    index = client.index("my-index")
    index.add_documents(
        [{"_id": "1", "title": "Hello"}],
        tensor_fields=["title"],
    )
    index.search("hello")

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the ``marqo``
value for ``db.system.name``. Vector-database-specific fields (such as the
number of documents, ``limit`` / ``top_k``, query vectors, or filters) are not
emitted because there is currently no stable semantic convention for them.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.marqo._wrap import _wrap
from opentelemetry.instrumentation.marqo.package import _instruments
from opentelemetry.instrumentation.marqo.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer, get_tracer

_MODULE = "marqo.index"
_INDEX_CLASS = "Index"

# Methods on ``marqo.index.Index`` that perform database operations against a
# single index. The index (collection) name is read from the instance rather
# than from the method arguments. Not every method exists on every supported
# ``marqo`` version, so instrumentation only wraps the methods actually present
# on the installed ``Index`` class.
_INDEX_METHODS: tuple[str, ...] = (
    "add_documents",
    "search",
    "delete_documents",
)


class MarqoInstrumentor(BaseInstrumentor):
    """An instrumentor for Marqo's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        from marqo.index import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            Index,
        )

        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        for method in _INDEX_METHODS:
            if hasattr(Index, method):
                wrap_function_wrapper(
                    _MODULE,
                    f"{_INDEX_CLASS}.{method}",
                    _wrap(tracer, method),
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        from marqo.index import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            Index,
        )

        for method in _INDEX_METHODS:
            if hasattr(Index, method):
                unwrap(Index, method)
