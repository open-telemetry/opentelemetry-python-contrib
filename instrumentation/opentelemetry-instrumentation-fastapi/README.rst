OpenTelemetry FastAPI Instrumentation
=======================================
|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-fastapi.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-fastapi/

This library provides automatic and manual instrumentation of FastAPI web frameworks,
instrumenting http requests served by applications utilizing the framework.
auto-instrumentation using the opentelemetry-instrumentation package is also supported.

Installation
------------

::

    pip install opentelemetry-instrumentation-fastapi

Usage
-----

Configure your ``TracerProvider`` and call ``FastAPIInstrumentor.instrument_app()``
**before** defining routes or handling requests. Instrumentation applied after route
registration will not capture spans for those routes.

.. code-block:: python

    from fastapi import FastAPI
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    # 1. Configure the TracerProvider first
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # 2. Create the FastAPI app
    app = FastAPI()

    # 3. Instrument the app before defining routes
    FastAPIInstrumentor.instrument_app(app)

    # 4. Define routes after instrumentation
    @app.get("/")
    async def root():
        return {"message": "Hello World"}

.. note::

    ``instrument_app()`` must be called after the ``FastAPI`` instance is created
    but before the application starts serving requests. Calling it after routes are
    registered is supported, but calling it after the application has started
    handling requests may result in missing spans.

Exclude URLs
------------

To exclude certain URLs from instrumentation, pass a comma-separated string of
regex patterns via the ``excluded_urls`` parameter:

.. code-block:: python

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz,/metrics")

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_