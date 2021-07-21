oxeye_opentelemetry Falcon Tracing
============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-falcon.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-falcon/

This library builds on the oxeye_opentelemetry WSGI middleware to track web requests
in Falcon applications.

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-falcon

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_FALCON_EXCLUDED_URLS`` with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_FALCON_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

Request attributes
********************
To extract certain attributes from Falcon's request object and use them as span attributes, set the environment variable ``OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS`` to a comma
delimited list of request attribute names. 

For example,

::

    export OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS='query_string,uri_template'

will extract path_info and content_type attributes from every traced request and add them as span attritbues.

Falcon Request object reference: https://falcon.readthedocs.io/en/stable/api/request_and_response.html#id1

References
----------

* `oxeye_opentelemetry Falcon Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/falcon/falcon.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
