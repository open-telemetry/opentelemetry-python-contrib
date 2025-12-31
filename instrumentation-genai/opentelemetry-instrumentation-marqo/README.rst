OpenTelemetry Marqo Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-marqo.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-marqo/

This library allows tracing requests made by the Marqo vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-marqo

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.marqo import MarqoInstrumentor
    import marqo

    # Enable instrumentation
    MarqoInstrumentor().instrument()

    # Use Marqo client normally
    mq = marqo.Client(url="http://localhost:8882")
    mq.index("my-index").add_documents([
        {"title": "Hello, world!", "_id": "doc1"}
    ])
    results = mq.index("my-index").search("hello")

Instrumented Operations
-----------------------

The following Marqo operations are instrumented:

- ``Index.add_documents`` - Add documents to an index
- ``Index.search`` - Vector similarity search
- ``Index.delete_documents`` - Delete documents from an index

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "marqo"
- ``db.operation`` = the operation name
- Operation-specific attributes (e.g., ``db.marqo.search.query``)

Query Result Events
-------------------

For search operations, result events are emitted for each hit with the hit metadata.

API
---
