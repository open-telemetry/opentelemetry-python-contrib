OpenTelemetry Weaviate Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-weaviate.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-weaviate/

This library allows tracing client-side operations against the
`Weaviate vector database <https://pypi.org/project/weaviate-client/>`_ made
through the ``weaviate-client`` library.

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``weaviate`` value for ``db.system.name``. Only the
standard database attributes ``db.system.name``, ``db.operation.name`` and
``db.collection.name`` are recorded (plus ``error.type`` on failures).
Vector-database-specific fields (such as the number of objects, ``limit`` /
``top_k``, query vectors, or filters) are **not** emitted because there is
currently no stable semantic convention for them.

Scope
-----

Only the ``weaviate-client`` **v4** collection-management operations on
``client.collections`` (``create``, ``get``, ``delete``, ``delete_all``,
``create_from_dict``, ``exists`` and ``list_all``) are instrumented.
Per-collection data and query operations on a live connection (such as
``collection.data.insert`` or ``collection.query.near_vector``) are out of
scope, because there is no stable vector semantic convention for them and they
require a running Weaviate server.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-weaviate

Usage
-----

.. code-block:: python

    import weaviate
    from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor

    WeaviateInstrumentor().instrument()

    client = weaviate.connect_to_local()
    client.collections.create("Article")
    client.collections.exists("Article")
    client.collections.delete("Article")

Uninstrument
------------

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor

    WeaviateInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    WeaviateInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Weaviate Python client <https://pypi.org/project/weaviate-client/>`_
* `OpenTelemetry Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
