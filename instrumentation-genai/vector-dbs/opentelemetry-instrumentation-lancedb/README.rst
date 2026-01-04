OpenTelemetry LanceDB Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-lancedb.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-lancedb/

This library allows tracing requests made by the LanceDB vector database client.

Installation
------------

::

    pip install opentelemetry-instrumentation-lancedb

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor
    import lancedb

    # Enable instrumentation
    LanceDBInstrumentor().instrument()

    # Use LanceDB client normally
    db = lancedb.connect("./lancedb")
    table = db.create_table("my_table", [{"vector": [1.0, 2.0], "text": "hello"}])
    table.add([{"vector": [3.0, 4.0], "text": "world"}])
    results = table.search([1.0, 2.0]).limit(10).to_list()

Instrumented Operations
-----------------------

The following LanceDB operations are instrumented:

- ``LanceTable.add`` - Add data to a table
- ``LanceTable.search`` - Vector similarity search
- ``LanceTable.delete`` - Delete data from a table

Span Attributes
---------------

Each operation records relevant span attributes:

- ``db.system`` = "lancedb"
- ``db.operation`` = the operation name
- Operation-specific attributes (e.g., ``db.lancedb.add.data_count``)

API
---
