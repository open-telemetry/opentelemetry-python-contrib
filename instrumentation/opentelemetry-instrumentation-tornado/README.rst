OpenTelemetry Tornado Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-tornado.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-tornado/

This library builds on the OpenTelemetry WSGI middleware to track web requests
in Tornado applications.

Installation
------------

::

    pip install opentelemetry-instrumentation-tornado

Configuration
-------------

The following environment variables are supported as configuration options:

- OTEL_PYTHON_TORNADO_EXCLUDED_URLS 

A comma separated list of paths that should not be automatically traced. For example, if this is set to 

::

    export OTEL_PYTHON_TORNADO_EXLUDED_URLS='/healthz,/ping'

Then any requests made to ``/healthz`` and ``/ping`` will not be automatically traced.

Request attributes
********************
To extract certain attributes from Tornado's request object and use them as span attributes, set the environment variable ``OTEL_PYTHON_TORNADO_TRACED_REQUEST_ATTRS`` to a comma
delimited list of request attribute names. 

For example,

::

    export OTEL_PYTHON_TORNADO_TRACED_REQUEST_ATTRS='uri,query'

will extract path_info and content_type attributes from every traced request and add them as span attributes.

Request/Response hooks
**********************

Tornado instrumentation supports extending tracing behaviour with the help of hooks.
Its ``instrument()`` method accepts three optional functions that get called back with the
created span and some other contextual information. Example:

.. code-block:: python

    # will be called for each incoming request to Tornado
    # web server. `handler` is an instance of
    # `tornado.web.RequestHandler`.
    def server_request_hook(span, handler):
        pass

    # will be called just before sending out a request with
    # `tornado.httpclient.AsyncHTTPClient.fetch`.
    # `request` is an instance of ``tornado.httpclient.HTTPRequest`.
    def client_request_hook(span, request):
        pass

    # will be called after a outgoing request made with
    # `tornado.httpclient.AsyncHTTPClient.fetch` finishes.
    # `response`` is an instance of ``Future[tornado.httpclient.HTTPResponse]`.
    def client_resposne_hook(span, future):
        pass

    # apply tornado instrumentation with hooks
    TornadoInstrumentor().instrument(
        server_request_hook=server_request_hook,
        client_request_hook=client_request_hook,
        client_response_hook=client_resposne_hook
    )

References
----------

* `OpenTelemetry Tornado Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/tornado/tornado.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
