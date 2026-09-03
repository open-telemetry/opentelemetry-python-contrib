OpenTelemetry unhandled exceptions instrumentation
==================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-exceptions.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-exceptions/

Installation
------------

::

    pip install opentelemetry-instrumentation-exceptions

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.exceptions import (
        UnhandledExceptionInstrumentor,
    )

    UnhandledExceptionInstrumentor().instrument()

This instrumentation captures uncaught process exceptions, uncaught thread
exceptions, and unhandled asyncio task exceptions and emits them as OpenTelemetry
logs.

Emitted records follow the exception log semantic conventions: the event name is
``exception``, and ``exception.type``, ``exception.message`` and
``exception.stacktrace`` are recorded as log record attributes.

The record body keeps carrying the stringified exception, so both
representations stay supported. It duplicates the ``exception.message``
attribute, but existing consumers reading the body are not broken.

References
----------

* `Semantic conventions for exceptions in logs <https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-logs/>`_

* `OpenTelemetry Python Contrib repository <https://github.com/open-telemetry/opentelemetry-python-contrib>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
