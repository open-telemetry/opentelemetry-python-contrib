OpenTelemetry Marqo Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-marqo.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-marqo/

This library allows tracing client-side operations against the
`Marqo vector database <https://pypi.org/project/marqo/>`_ made through
the ``marqo`` library.

The instrumentation emits generic OpenTelemetry database spans following the
`Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``marqo`` value for ``db.system.name``. Only the standard
database attributes ``db.system.name``, ``db.operation.name`` and
``db.collection.name`` are recorded (plus ``error.type`` on failures).
Vector-database-specific fields (such as the number of documents, ``limit`` /
``top_k``, query vectors, or filters) are **not** emitted because there is
currently no stable semantic convention for them.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-marqo

Usage
-----

.. code-block:: python

    import marqo
    from opentelemetry.instrumentation.marqo import MarqoInstrumentor

    MarqoInstrumentor().instrument()

    client = marqo.Client(url="http://localhost:8882")
    client.create_index("my-index")
    index = client.index("my-index")
    index.add_documents(
        [{"_id": "1", "title": "Hello"}],
        tensor_fields=["title"],
    )
    index.search("hello")

The instrumented operations are ``add_documents``, ``search`` and
``delete_documents`` on ``marqo.index.Index``. The index (collection) name is
read from the ``Index`` instance and recorded as ``db.collection.name``.

Uninstrument
------------

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.marqo import MarqoInstrumentor

    MarqoInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    MarqoInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Marqo Python client <https://pypi.org/project/marqo/>`_
* `OpenTelemetry Database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
