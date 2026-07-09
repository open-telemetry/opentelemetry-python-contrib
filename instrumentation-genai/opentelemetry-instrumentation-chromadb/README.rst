OpenTelemetry ChromaDB Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-chromadb.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-chromadb/

This library allows tracing requests made by the
`ChromaDB client library <https://pypi.org/project/chromadb/>`_.

The emitted telemetry follows the standard OpenTelemetry
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``chromadb`` value for ``db.system.name``.

Each instrumented ChromaDB operation produces a single ``CLIENT`` span with the
following attributes:

- ``db.system.name`` - always ``chromadb``.
- ``db.operation.name`` - the ChromaDB operation, one of ``add``, ``get``,
  ``query``, ``delete``, ``update``, ``upsert``, ``peek``, ``count``,
  ``modify``, ``create_collection``, ``get_or_create_collection`` or
  ``delete_collection``.
- ``db.collection.name`` - the collection name, when available.
- ``error.type`` - the exception class name, set only when the operation fails.

The span name is ``"{db.operation.name} {db.collection.name}"`` (or just the
operation name when no collection is known).

.. note::

   Only generic, standardized ``db.*`` attributes are emitted. Vector-database
   specific fields (for example the number of embeddings, ``n_results`` /
   ``top_k``, ids, or ``where`` filters) are intentionally **not** recorded
   because there is currently no stable OpenTelemetry semantic convention for
   them. Richer attributes will be added once such conventions are
   standardized.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-chromadb

Usage
-----

.. code-block:: python

    import chromadb
    from opentelemetry.instrumentation.chromadb import ChromaInstrumentor

    ChromaInstrumentor().instrument()

    client = chromadb.Client()
    collection = client.create_collection("my_collection")
    collection.add(ids=["id1"], documents=["hello world"])
    results = collection.query(query_texts=["hello"], n_results=1)

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.chromadb import ChromaInstrumentor

    ChromaInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    ChromaInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `ChromaDB <https://pypi.org/project/chromadb/>`_
* `OpenTelemetry Database Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
