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

References
----------

* `OpenTelemetry Python Contrib repository <https://github.com/open-telemetry/opentelemetry-python-contrib>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
