OpenTelemetry Pinecone Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-pinecone.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-pinecone/

This library allows tracing data-plane operations against the
`Pinecone vector database <https://pypi.org/project/pinecone/>`_.

The emitted telemetry follows the generic OpenTelemetry
`database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
(``db.*``), using the ``pinecone`` value for ``db.system.name``.

.. note::
   This instrumentation emits **only** generic ``db.*`` attributes. Pinecone is
   a vector database, but there is currently no stable OpenTelemetry semantic
   convention for vector-specific fields (query vectors, ``top_k``, match
   scores, etc.), so none of those are captured.

The following attributes are emitted on each span:

* ``db.system.name`` — always the literal ``"pinecone"``.
* ``db.operation.name`` — the invoked method (``query``, ``upsert``,
  ``delete``, ``fetch``, ``update`` or ``describe_index_stats``).
* ``db.collection.name`` — the Pinecone index name, when derivable from the
  client host.
* ``db.namespace`` — the Pinecone namespace, when supplied to the call.
* ``error.type`` — set on failed calls.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-pinecone

Usage
-----

.. code-block:: python

    from pinecone import Pinecone
    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor

    PineconeInstrumentor().instrument()

    pc = Pinecone(api_key="...")
    index = pc.Index(host="https://my-index-abc.svc.pinecone.io")
    index.query(vector=[0.1, 0.2, 0.3], top_k=3, namespace="ns")

Instrument **before** creating ``Index`` clients: the Pinecone SDK binds some
data-plane methods per-instance at construction time, so clients created prior
to instrumentation may not be fully traced.

Uninstrument
------------

.. code-block:: python

    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor

    PineconeInstrumentor().instrument()
    # ...
    PineconeInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Pinecone Python client <https://pypi.org/project/pinecone/>`_
* `OpenTelemetry database semantic conventions <https://opentelemetry.io/docs/specs/semconv/database/>`_
