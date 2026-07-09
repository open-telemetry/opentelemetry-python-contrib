# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
LanceDB instrumentation supporting `lancedb`, it can be enabled by
using ``LanceDBInstrumentor``.

.. _lancedb: https://pypi.org/project/lancedb/

Usage
-----

.. code:: python

    import lancedb
    from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor

    LanceDBInstrumentor().instrument()

    db = lancedb.connect("/tmp/lancedb")
    table = db.create_table(
        "my_table",
        data=[{"id": 1, "vector": [0.1, 0.2, 0.3, 0.4]}],
    )
    table.add([{"id": 2, "vector": [0.5, 0.6, 0.7, 0.8]}])
    table.search([0.1, 0.2, 0.3, 0.4]).limit(1).to_list()
    table.delete("id = 1")

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_, using the ``lancedb``
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
from opentelemetry.instrumentation.lancedb._wrap import _wrap
from opentelemetry.instrumentation.lancedb.package import _instruments
from opentelemetry.instrumentation.lancedb.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer, get_tracer

_MODULE = "lancedb.table"
_TABLE_CLASS = "LanceTable"

# Methods on ``lancedb.table.LanceTable`` that represent database operations.
# These are synchronous methods; ``LanceTable`` has no async variants (async
# access is provided through the separate ``AsyncTable`` API), so only the
# synchronous wrapper is used. Not every method is guaranteed to exist on every
# supported ``lancedb`` version, so instrumentation only wraps the methods
# actually present on the installed table class.
_TABLE_METHODS: tuple[str, ...] = (
    "add",
    "search",
    "delete",
)


class LanceDBInstrumentor(BaseInstrumentor):
    """An instrumentor for LanceDB's table library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        import lancedb.table  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        tracer_provider = kwargs.get("tracer_provider")
        tracer: Tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        table_class = getattr(lancedb.table, _TABLE_CLASS, None)
        for method in _TABLE_METHODS:
            if table_class is not None and hasattr(table_class, method):
                wrap_function_wrapper(
                    _MODULE,
                    f"{_TABLE_CLASS}.{method}",
                    _wrap(tracer, method),
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        import lancedb.table  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        table_class = getattr(lancedb.table, _TABLE_CLASS, None)
        for method in _TABLE_METHODS:
            if table_class is not None and hasattr(table_class, method):
                unwrap(table_class, method)
