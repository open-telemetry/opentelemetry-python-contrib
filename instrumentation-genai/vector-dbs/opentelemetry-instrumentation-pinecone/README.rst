OpenTelemetry Pinecone Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-pinecone.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-pinecone/

This library allows tracing requests made by the Pinecone vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-pinecone

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor
    from pinecone import Pinecone

    # Enable instrumentation
    PineconeInstrumentor().instrument()

    # Use Pinecone client normally
    pc = Pinecone(api_key="your-api-key")
    index = pc.Index("my-index")
    index.upsert(vectors=[{"id": "vec1", "values": [0.1, 0.2, 0.3]}])
    results = index.query(vector=[0.1, 0.2, 0.3], top_k=10)

Instrumented Operations
-----------------------

The following Pinecone operations are instrumented:

- ``Index.query`` - Vector similarity search
- ``Index.upsert`` - Insert or update vectors
- ``Index.delete`` - Delete vectors
- ``GRPCIndex.query`` - Vector similarity search (gRPC)
- ``GRPCIndex.upsert`` - Insert or update vectors (gRPC)
- ``GRPCIndex.delete`` - Delete vectors (gRPC)

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "pinecone"
- ``db.operation`` = the operation name
- ``server.address`` = the Pinecone host address
- Operation-specific attributes (e.g., ``db.pinecone.query.top_k``)

Metrics
-------

When metrics are enabled (default), the following metrics are recorded:

- ``db.pinecone.query.duration`` - Duration of query operations
- ``db.pinecone.query.scores`` - Scores returned from queries
- ``db.pinecone.usage.read_units`` - Read units consumed
- ``db.pinecone.usage.write_units`` - Write units consumed

Set ``OTEL_INSTRUMENTATION_GENAI_METRICS_ENABLED=false`` to disable metrics.

Query Result Events
-------------------

For query operations, result events are emitted with:

- ``db.query.result.id`` - Result vector ID
- ``db.query.result.score`` - Similarity score
- ``db.query.result.metadata`` - Associated metadata
- ``db.query.result.vector`` - Retrieved vector values

API
---
