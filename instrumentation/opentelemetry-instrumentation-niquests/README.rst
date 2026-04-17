OpenTelemetry Niquests Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-niquests.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-niquests/

This library allows tracing HTTP requests made by the
`niquests <https://niquests.readthedocs.io/>`_ library.

Niquests is a drop-in replacement for the ``requests`` library with
native async support, HTTP/2, and HTTP/3 capabilities. Both synchronous
and asynchronous interfaces are instrumented.

Lazy responses (e.g. ``Session(multiplexed=True)``) receive a span and
connection-level attributes (IP, TLS) but **status code and response headers
are not captured** because they are not yet available.

Installation
------------

::

     pip install opentelemetry-instrumentation-niquests

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_NIQUESTS_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_NIQUESTS_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

References
----------

* `OpenTelemetry niquests Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/niquests/niquests.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
