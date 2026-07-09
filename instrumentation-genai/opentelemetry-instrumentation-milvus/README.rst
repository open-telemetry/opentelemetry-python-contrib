OpenTelemetry Milvus Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-milvus.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-milvus/

This library allows tracing client-side operations against the
`Milvus vector database <https://pypi.org/project/pymilvus/>`_ made through
the ``pymilvus`` library.

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``milvus`` value for ``db.system.name``. Only the standard
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

    pip install opentelemetry-instrumentation-milvus

Usage
-----

.. code-block:: python

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

The synchronous ``MilvusClient`` is instrumented.

Uninstrument
------------

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.milvus import MilvusInstrumentor

    MilvusInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    MilvusInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Milvus Python client <https://pypi.org/project/pymilvus/>`_
* `OpenTelemetry Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
