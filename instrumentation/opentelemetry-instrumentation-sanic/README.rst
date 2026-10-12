OpenTelemetry Sanic Integration
===============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-sanic.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-sanic/

This library allows tracing HTTP requests made by the
`Sanic <https://sanic.dev/>`_ framework.

Installation
------------

::

     pip install opentelemetry-instrumentation-sanic

Usage
-----

::

    from sanic import Sanic, response
    from opentelemetry.instrumentation.sanic import SanicInstrumentor

    SanicInstrumentor().instrument()

    app = Sanic("myapp")

    @app.get("/")
    async def hello(request):
        return response.text("Hello, world")

Tracing is applied to every ``Sanic`` application (and ``Sanic`` subclass) that
is created after the instrumentor ran, because the instrumentation registers its
middleware from ``Sanic.__init__``.

Server spans cover the whole request lifecycle, including request and response
middleware registered by the application, and are named after the matched route
template, e.g. ``GET /items/<item_id:int>``.

WebSocket routes are not instrumented.

References
----------

* `OpenTelemetry Sanic Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sanic/sanic.html>`_
* `Sanic <https://sanic.dev/>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
