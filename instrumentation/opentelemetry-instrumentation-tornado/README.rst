OpenTelemetry Tornado Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-tornado.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-tornado/

This library builds on the OpenTelemetry WSGI middleware to track web requests
in Tornado applications.

Installation
------------

::

    pip install opentelemetry-instrumentation-tornado

Configuration
-------------

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

* `OpenTelemetry Tornado Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/tornado/tornado.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
