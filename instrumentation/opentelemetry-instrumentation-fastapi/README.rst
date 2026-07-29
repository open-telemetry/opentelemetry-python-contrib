OpenTelemetry FastAPI Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-fastapi.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-fastapi/


This library provides automatic and manual instrumentation of FastAPI web frameworks,
instrumenting http requests served by applications utilizing the framework.

Automatic instrumentation using the
`opentelemetry-instrumentation <https://pypi.org/project/opentelemetry-instrumentation/>`_
package is also supported.

Installation
------------

::

    pip install opentelemetry-instrumentation-fastapi

For the ``opentelemetry-instrument`` launcher, install the distro and an OTLP
exporter as well:

::

    pip install opentelemetry-distro opentelemetry-exporter-otlp
    opentelemetry-bootstrap -a install
    opentelemetry-instrument uvicorn myapp:app

Manual instrumentation is available when the application creates its own
FastAPI instance:

.. code-block:: python

    import fastapi
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app = fastapi.FastAPI()
    FastAPIInstrumentor.instrument_app(app)

Configuration and propagation
-----------------------------

The launcher and SDK read the standard OpenTelemetry environment variables.
For example, these configure the service name and OTLP destination without
application-specific setup:

::

    OTEL_SERVICE_NAME=my-fastapi-service
    OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
    OTEL_EXPORTER_OTLP_PROTOCOL=grpc

Incoming HTTP trace context is extracted by the ASGI middleware, so normal
FastAPI requests propagate context automatically. WebSocket routes are also
instrumented as ASGI connections (including the handshake); the integration
creates a server span for the route rather than one span per WebSocket
message.

Logging is a separate signal. FastAPI instrumentation does not turn log
records into span events. To correlate application logs with request spans,
install and enable the
`logging instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html>`_:

::

    pip install opentelemetry-instrumentation-logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=True)

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
