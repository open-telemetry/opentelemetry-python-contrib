OpenTelemetry Exceptions Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-exceptions.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-exceptions/

This library emits OpenTelemetry logs for uncaught exceptions and unhandled
asyncio task exceptions.

Installation
------------

::

    pip install opentelemetry-instrumentation-exceptions

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.exceptions import (
        UnhandledExceptionInstrumentor,
    )

    UnhandledExceptionInstrumentor().instrument()

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
