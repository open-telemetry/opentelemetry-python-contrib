OpenTelemetry Qdrant Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-qdrant.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-qdrant/

This library allows tracing client-side operations against the
`Qdrant vector database <https://pypi.org/project/qdrant-client/>`_ made through
the ``qdrant-client`` library.

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``qdrant`` value for ``db.system.name``. Only the standard
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

    pip install opentelemetry-instrumentation-qdrant

Usage
-----

.. code-block:: python

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

Both the synchronous ``QdrantClient`` and the asynchronous ``AsyncQdrantClient``
are instrumented.

Uninstrument
------------

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.qdrant import QdrantInstrumentor

    QdrantInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    QdrantInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Qdrant Python client <https://pypi.org/project/qdrant-client/>`_
* `OpenTelemetry Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
