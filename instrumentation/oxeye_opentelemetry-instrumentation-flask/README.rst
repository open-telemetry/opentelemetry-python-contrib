oxeye_opentelemetry Flask Tracing
===========================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-flask.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-flask/

This library builds on the oxeye_opentelemetry WSGI middleware to track web requests
in Flask applications.

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-flask

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_FLASK_EXCLUDED_URLS`` with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_FLASK_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

References
----------

* `oxeye_opentelemetry Flask Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/stable/instrumentation/flask/flask.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
