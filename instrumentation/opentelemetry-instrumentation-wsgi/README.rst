OpenTelemetry WSGI Middleware
=============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-wsgi.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-wsgi/


This library provides a WSGI middleware that can be used on any WSGI framework
(such as Django / Flask) to track requests timing through OpenTelemetry.

Installation
------------

::

    pip install opentelemetry-instrumentation-wsgi

Configuration
-------------

Request/Response hooks
**********************

Utilize request/reponse hooks to execute custom logic to be performed before/after performing a request. Environ is an instance of WSGIEnvironment.
Response_headers is a list of key-value (tuples) representing the response headers returned from the response.

.. code-block:: python

    def request_hook(span: Span, environ: WSGIEnvironment):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span: Span, environ: WSGIEnvironment, status: str, response_headers: List):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    OpenTelemetryMiddleware(request_hook=request_hook, response_hook=response_hook)

References
----------

* `OpenTelemetry WSGI Middleware <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `WSGI <https://www.python.org/dev/peps/pep-3333>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
