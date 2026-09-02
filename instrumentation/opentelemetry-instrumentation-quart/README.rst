OpenTelemetry Quart Instrumentation
====================================

This library provides automatic OpenTelemetry instrumentation for Quart applications.

Installation
------------

::

    pip install opentelemetry-instrumentation-quart

Usage
-----

.. code-block:: python

    from quart import Quart
    from opentelemetry.instrumentation.quart import QuartInstrumentor

    app = Quart(__name__)

    QuartInstrumentor.instrument_app(app)

Automatic instrumentation is also supported through ``opentelemetry-instrument``.