OpenTelemetry Milvus Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-milvus.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-milvus/

This library allows tracing requests made by the Milvus vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-milvus

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.milvus import MilvusInstrumentor
    from pymilvus import MilvusClient

    # Enable instrumentation
    MilvusInstrumentor().instrument()

    # Use Milvus client normally
    client = MilvusClient("./milvus.db")
    client.create_collection(
        collection_name="my_collection",
        dimension=128
    )
    client.insert(
        collection_name="my_collection",
        data=[{"id": 1, "vector": [0.1] * 128}]
    )
    results = client.search(
        collection_name="my_collection",
        data=[[0.1] * 128],
        limit=10
    )

Instrumented Operations
-----------------------

The following Milvus operations are instrumented:

- ``MilvusClient.create_collection`` - Create a new collection
- ``MilvusClient.insert`` - Insert vectors
- ``MilvusClient.upsert`` - Insert or update vectors
- ``MilvusClient.delete`` - Delete vectors
- ``MilvusClient.search`` - Vector similarity search
- ``MilvusClient.get`` - Get vectors by ID
- ``MilvusClient.query`` - Query with filter expressions
- ``MilvusClient.hybrid_search`` - Hybrid search with multiple vectors

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "milvus"
- ``db.operation`` = the operation name
- Operation-specific attributes (e.g., ``db.milvus.search.collection_name``)

Metrics
-------

When metrics are enabled (default), the following metrics are recorded:

- ``db.milvus.query.duration`` - Duration of query operations
- ``db.milvus.search.distance`` - Distance scores from search results
- ``db.milvus.usage.insert_units`` - Insert operation counts
- ``db.milvus.usage.upsert_units`` - Upsert operation counts
- ``db.milvus.usage.delete_units`` - Delete operation counts

Set ``OTEL_INSTRUMENTATION_GENAI_METRICS_ENABLED=false`` to disable metrics.

Search Result Events
--------------------

For search operations, result events are emitted with:

- ``db.search.result.query_id`` - Query index
- ``db.search.result.id`` - Result vector ID
- ``db.search.result.distance`` - Distance score
- ``db.search.result.entity`` - Entity data

API
---
