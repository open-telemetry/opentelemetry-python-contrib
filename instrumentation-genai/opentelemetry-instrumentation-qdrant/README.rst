OpenTelemetry Qdrant Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-qdrant.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-qdrant/

This library allows tracing requests made by the Qdrant vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-qdrant

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.qdrant import QdrantInstrumentor
    from qdrant_client import QdrantClient

    # Enable instrumentation
    QdrantInstrumentor().instrument()

    # Use Qdrant client normally
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="my_collection",
        vectors_config={"size": 4, "distance": "Cosine"}
    )
    client.upsert(
        collection_name="my_collection",
        points=[
            {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"name": "doc1"}}
        ]
    )
    results = client.search(
        collection_name="my_collection",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=10
    )

Async Support
-------------

The instrumentation also supports ``AsyncQdrantClient``:

.. code-block:: python

    from qdrant_client import AsyncQdrantClient

    async def main():
        client = AsyncQdrantClient(":memory:")
        results = await client.search(
            collection_name="my_collection",
            query_vector=[0.1, 0.2, 0.3, 0.4],
            limit=10
        )

Instrumented Operations
-----------------------

The following Qdrant operations are instrumented for both sync and async clients:

**Write Operations:**

- ``upsert`` - Insert or update points
- ``add`` - Add documents
- ``upload_points`` - Upload points
- ``upload_records`` - Upload records
- ``upload_collection`` - Upload collection
- ``delete`` - Delete points
- ``delete_vectors`` - Delete vectors
- ``delete_payload`` - Delete payload
- ``set_payload`` - Set payload
- ``overwrite_payload`` - Overwrite payload
- ``update_vectors`` - Update vectors
- ``batch_update_points`` - Batch update points

**Search Operations:**

- ``search`` - Vector similarity search
- ``search_batch`` - Batch search
- ``search_groups`` - Search with grouping
- ``query`` - Query points
- ``query_batch`` - Batch query
- ``discover`` - Discover points
- ``discover_batch`` - Batch discover
- ``recommend`` - Get recommendations
- ``recommend_batch`` - Batch recommendations
- ``recommend_groups`` - Recommendations with grouping
- ``scroll`` - Scroll through points

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "qdrant"
- ``db.operation`` = the operation name
- ``db.qdrant.collection_name`` = the collection name
- Operation-specific attributes (e.g., ``db.qdrant.upsert.points_count``)

API
---
