OpenTelemetry ChromaDB Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-chromadb.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-chromadb/

This library allows tracing requests made by the ChromaDB vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-chromadb

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.chromadb import ChromaInstrumentor
    import chromadb

    # Enable instrumentation
    ChromaInstrumentor().instrument()

    # Use ChromaDB client normally
    client = chromadb.Client()
    collection = client.create_collection("my_collection")
    collection.add(
        documents=["Hello, world!"],
        metadatas=[{"source": "example"}],
        ids=["id1"]
    )
    results = collection.query(query_texts=["Hello"], n_results=1)

Instrumented Operations
-----------------------

The following ChromaDB operations are instrumented:

- ``Collection.add`` - Add documents/embeddings to a collection
- ``Collection.get`` - Retrieve documents by ID
- ``Collection.peek`` - Preview documents in a collection
- ``Collection.query`` - Vector similarity search
- ``Collection.modify`` - Modify collection metadata
- ``Collection.update`` - Update documents
- ``Collection.upsert`` - Insert or update documents
- ``Collection.delete`` - Delete documents

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "chromadb"
- ``db.operation`` = the operation name
- Operation-specific attributes (e.g., ``db.chroma.query.n_results``)

Query Result Events
-------------------

For query operations, result events are emitted with:

- ``db.query.result.id`` - Result document ID
- ``db.query.result.distance`` - Similarity distance
- ``db.query.result.document`` - Retrieved document text
- ``db.query.result.metadata`` - Associated metadata

API
---
