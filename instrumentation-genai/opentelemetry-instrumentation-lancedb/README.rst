OpenTelemetry LanceDB Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-lancedb.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-lancedb/

This library allows tracing client-side operations against the
`LanceDB vector database <https://pypi.org/project/lancedb/>`_ made through
the ``lancedb`` library.

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``lancedb`` value for ``db.system.name``. Only the standard
database attributes ``db.system.name``, ``db.operation.name`` and
``db.collection.name`` are recorded (plus ``error.type`` on failures).
Vector-database-specific fields (such as the number of vectors, ``limit`` /
``top_k``, query vectors, or filters) are **not** emitted because there is
currently no stable semantic convention for them.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-lancedb

Usage
-----

.. code-block:: python

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

The synchronous ``lancedb.table.LanceTable`` ``add``, ``search`` and ``delete``
operations are instrumented.

Uninstrument
------------

To uninstrument tables, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor

    LanceDBInstrumentor().instrument()
    # ...

    # Uninstrument all tables
    LanceDBInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `LanceDB Python client <https://pypi.org/project/lancedb/>`_
* `OpenTelemetry Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
