OpenTelemetry CherryPy Tracing
============================

|pypi|

.. |pypi| image:: TODO
   :target: TODO

This library builds on the OpenTelemetry WSGI middleware to track web requests
in CherryPy applications.

Installation
------------

::

    pip install opentelemetry-instrumentation-cherrypy

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_CHERRYPY_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_CHERRYPY_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

References
----------

* `OpenTelemetry CherryPy Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/cherrypy/cherrypy.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
