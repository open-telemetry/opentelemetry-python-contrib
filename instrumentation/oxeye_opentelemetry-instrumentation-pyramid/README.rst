oxeye_opentelemetry Pyramid Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-pyramid.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-pyramid/

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-pyramid

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_PYRAMID_EXCLUDED_URLS`` with comma delimited regexes representing which URLs to exclude.

For example, 

::

    export OTEL_PYTHON_PYRAMID_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

References
----------
* `oxeye_opentelemetry Pyramid Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pyramid/pyramid.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_

