OpenTelemetry Rich Console Exporter
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-exporter-richconsole.svg
   :target: https://pypi.org/project/opentelemetry-exporter-richconsole/

This library is a console exporter that renders `OpenTelemetry`_ spans to the
terminal using `Rich`_. When used with a ``BatchSpanProcessor``,
spans of the same trace are shown as a single Rich *tree*: the trace is the
root and every span appears as a child node together with its kind, status,
events, attributes and resource properties. When used with a
``SimpleSpanProcessor``, every span is printed as a flat list entry instead.

Installation
------------

::

    pip install opentelemetry-exporter-richconsole

Quick start
-----------

The exporter implements the ``SpanExporter`` interface and is normally
attached to a ``BatchSpanProcessor`` so that the complete trace can be
rendered as a tree once the batch is flushed:

.. code:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.richconsole import RichConsoleSpanExporter

    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)

    tracer.add_span_processor(BatchSpanProcessor(RichConsoleSpanExporter()))

    with tracer.start_as_current_span("hello"):
        pass

The rendered tree for the example above looks like:

.. code:: text

    Trace 4bf92f3577b34da6a3ce929d0e0e4736
    └── [10:12:30.456789] hello, span 6e0c63257de34c92
        └── Kind : INTERNAL

Output format
-------------

Tree view (BatchSpanProcessor)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each trace becomes a tree whose root is labelled ``Trace <trace-id>``. Every
span is a node labelled with the span's start time, name and span id:

.. code:: text

    [10:12:30.456789] hello, span 6e0c63257de34c92

Depending on the span, the following children are attached to each span node:

* ``Kind`` — the span kind (``INTERNAL``, ``SERVER``, ``CLIENT``, ...).
* ``Status`` — only when the status is set; non-``OK`` status codes are
  rendered in red, and the status description is shown below it.
* ``Description`` — the status description (``Status.description``), when
  present.
* ``Events`` — one node per event, with the event name and each attribute as
  a key/value pair.
* ``Attributes`` — every span attribute as a key/value pair. The special
  ``db.statement`` attribute is rendered as highlighted SQL (see
  `SQL statement highlighting`_).
* ``Resources`` — the span's resource attributes (``service.name``,
  ``telemetry.sdk.*``, ...), unless suppressed via ``suppress_resource``.

List view (SimpleSpanProcessor)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With a ``SimpleSpanProcessor``, spans are exported one at a time, so a
tree cannot be assembled. Each span is printed as a flat list entry that still
contains the same kind/status/events/attributes/resource information.

Customizing the output
----------------------

Constructor parameters
~~~~~~~~~~~~~~~~~~~~~~

The exporter accepts two optional parameters:

.. code:: python

    RichConsoleSpanExporter(service_name=None, suppress_resource=False)

* ``suppress_resource=True`` omits the ``Resources`` node from every span,
  which is useful when the output is dominated by resource attributes.
* ``service_name`` is kept for forward compatibility; the resource attributes
  (including ``service.name`` when set on the resource) are read directly
  from the exported spans.

SQL statement highlighting
~~~~~~~~~~~~~~~~~~~~~~~~~~

Span attributes are printed as plain key/value pairs, with one exception: the
``db.statement`` attribute is rendered with Rich's ``Syntax`` highlighter
using the ``sql`` language, so query strings are colored per SQL syntax rules
in terminals that support it.

Rich rendering
~~~~~~~~~~~~~~

All output is rendered through a Rich ``rich.console.Console`` instance
writing to stdout. That means colors, styles and layout adapt automatically
to the capabilities of the terminal (TrueColor, 256-color and monochrome
terminals are all supported), and no ANSI codes are emitted when the output
is not a TTY. The tree structure, the ``[cyan]``/``[blue]``/``[red]`` label
styles and the SQL highlighting shown above are built with Rich primitives
(``Tree``, ``Text`` and ``Syntax``).

Examples
--------

A span with events, attributes and a SQL statement:

.. code:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.richconsole import RichConsoleSpanExporter
    from opentelemetry.semconv._incubating.attributes.db_attributes import DB_STATEMENT

    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer("shop")

    tracer.add_span_processor(BatchSpanProcessor(RichConsoleSpanExporter()))

    with tracer.start_as_current_span("find_user") as span:
        span.set_attribute("user.id", 42)
        span.set_attribute(DB_STATEMENT, "SELECT * FROM users WHERE id = 42")
        span.add_event("cache.miss", {"key": "user:42"})

Example output:

.. code:: text

    Trace 4bf92f3577b34da6a3ce929d0e0e4736
    └── [10:12:30.456789] find_user, span 6e0c63257de34c92
        ├── Kind : INTERNAL
        ├── Status : OK
        ├── Events :
        │   └── cache.miss
        │       └── key : user:42
        ├── Attributes :
        │   ├── user.id : 42
        │   └── db.statement :
        │       SELECT * FROM users WHERE id = 42
        └── Resources :
            ├── service.name : unknown_service
            └── telemetry.sdk.version : 1.x.y

.. _Rich: https://rich.readthedocs.io/
.. _OpenTelemetry: https://github.com/open-telemetry/opentelemetry-python/

References
----------

* `Rich <https://rich.readthedocs.io/>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
