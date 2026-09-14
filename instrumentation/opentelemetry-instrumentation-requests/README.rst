OpenTelemetry Requests Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-requests.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-requests/

This library allows tracing HTTP requests made by the
`requests <https://requests.readthedocs.io/en/master/>`_ library.

Installation
------------

::

     pip install opentelemetry-instrumentation-requests

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_REQUESTS_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

Request/Response hooks
**********************

``RequestsInstrumentor().instrument`` accepts optional ``request_hook`` and ``response_hook`` callbacks.
The request hook receives the span and the live ``requests.PreparedRequest`` after the span is created and
before OpenTelemetry injects propagation headers. Because this is the same request object that ``requests``
sends, mutations made by the hook can change the outbound request.

Propagation runs after the request hook, so values written by the configured propagator can replace values
written by the hook. Avoid copying inbound headers wholesale into an outbound request; preserve headers owned
by the application or connector unless the hook intentionally owns them.

The response hook receives the span, the prepared request, and the ``requests.Response`` before the span is
finished.

For example:

::

    def request_hook(span, request):
        request.headers["X-Request-Source"] = "example"

    RequestsInstrumentor().instrument(request_hook=request_hook)

References
----------

* `OpenTelemetry requests Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
