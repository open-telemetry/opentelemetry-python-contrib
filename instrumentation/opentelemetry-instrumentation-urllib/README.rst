OpenTelemetry urllib Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-urllib.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-urllib/

This library allows tracing HTTP requests made by the
`urllib <https://docs.python.org/3/library/urllib.html>`_ library.

Installation
------------

::

     pip install opentelemetry-instrumentation-urllib

Configuration
-------------

Request/Response hooks
**********************

The urllib instrumentation supports extending tracing behavior with the help of
request and response hooks. These are functions that are called back by the instrumentation
right after a Span is created for a request and right before the span is finished processing a response respectively.
The hooks can be configured as follows:

.. code:: python

    from opentelemetry.instrumentation.urllib import URLLibInstrumentor

    # `request_obj` is an instance of urllib.request.Request
    def request_hook(span, request_obj):
        pass

    # `request_obj` is an instance of urllib.request.Request
    # `response` is an instance of http.client.HTTPResponse
    def response_hook(span, request_obj, response):
        pass

    URLLibInstrumentor().instrument(
        request_hook=request_hook, response_hook=response_hook
    )

Exclude lists
*************

To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_URLLIB_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_URLLIB_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

Semantic Conventions
********************

By default, this instrumentation emits the **old experimental** HTTP semantic conventions.
You can opt in to the stable conventions by setting the ``OTEL_SEMCONV_STABILITY_OPT_IN``
environment variable. This is a comma-separated list of opt-in values:

- ``http`` — Emit the new, stable HTTP and networking conventions **only**. Stop emitting the old experimental conventions.
- ``http/dup`` — Emit **both** the old experimental and the new stable conventions, allowing for a seamless transition.

For example,

::

    export OTEL_SEMCONV_STABILITY_OPT_IN="http"

If the environment variable is not set, the old experimental HTTP semantic conventions will be used.

References
----------

* `OpenTelemetry urllib Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/urllib/urllib.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
