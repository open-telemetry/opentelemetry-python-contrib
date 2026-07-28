OpenTelemetry Rich Console Exporter
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-exporter-richconsole.svg
   :target: https://pypi.org/project/opentelemetry-exporter-richconsole/

This library is a console exporter using the Rich tree view. When used with a batch span processor, the rich console exporter will show the trace as a 
tree and all related spans as children within the tree, including properties.

Installation
------------

::

    pip install opentelemetry-exporter-richconsole


Quick start
-----------

Create a provider, attach the exporter to a span processor, and start a span:

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.exporter.richconsole import RichConsoleSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(
        SimpleSpanProcessor(RichConsoleSpanExporter())
    )
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("checkout") as span:
        span.set_attribute("cart.items", 2)

The exporter prints completed spans to stdout. Use
``BatchSpanProcessor(RichConsoleSpanExporter())`` when you want related spans
to be rendered as a tree; ``SimpleSpanProcessor`` prints each completed span
as it ends, which is useful for short-lived scripts and local debugging.


What is rendered
----------------

Each trace is rendered as a Rich tree. A span node can include:

* span kind and status (including a status description when present);
* span attributes and event attributes;
* resource attributes, such as the service name; and
* SQL syntax highlighting for the ``db.statement`` attribute.

Child spans are attached to their parent when the exporter receives the batch
together. A span whose parent is not in the exported batch becomes a new root.


Configuration
-------------

``RichConsoleSpanExporter`` accepts ``suppress_resource=True`` to hide resource
attributes when the output is too verbose for a local console:

.. code-block:: python

    exporter = RichConsoleSpanExporter(suppress_resource=True)

The default is ``False``. Resource attributes remain enabled by default so the
tree includes useful context such as ``service.name``. The exporter writes to
Rich's standard ``Console`` and returns ``SpanExportResult.SUCCESS`` after
printing a non-empty batch.


.. _Rich: https://rich.readthedocs.io/
.. _OpenTelemetry: https://github.com/open-telemetry/opentelemetry-python/


References
----------

* `Rich <https://rich.readthedocs.io/>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
