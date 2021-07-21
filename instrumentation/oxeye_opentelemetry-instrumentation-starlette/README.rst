oxeye_opentelemetry Starlette Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-starlette.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-starlette/


This library provides automatic and manual instrumentation of Starlette web frameworks,
instrumenting http requests served by applications utilizing the framework.

auto-instrumentation using the oxeye_opentelemetry-instrumentation package is also supported.

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-starlette

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_STARLETTE_EXCLUDED_URLS`` with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_STARLETTE_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.


Usage
-----

.. code-block:: python

    from oxeye_opentelemetry.instrumentation.starlette import StarletteInstrumentor
    from starlette import applications
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    def home(request):
        return PlainTextResponse("hi")

    app = applications.Starlette(
        routes=[Route("/foobar", home)]
    )
    StarletteInstrumentor.instrument_app(app)


References
----------

* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
