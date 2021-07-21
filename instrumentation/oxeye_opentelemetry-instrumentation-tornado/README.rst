oxeye_opentelemetry Tornado Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-tornado.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-tornado/

This library builds on the oxeye_opentelemetry WSGI middleware to track web requests
in Tornado applications.

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-tornado

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

References
----------

* `oxeye_opentelemetry Tornado Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/tornado/tornado.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
