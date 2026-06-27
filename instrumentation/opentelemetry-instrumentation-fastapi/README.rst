OpenTelemetry FastAPI Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-fastapi.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-fastapi/


This library provides automatic and manual instrumentation of FastAPI web frameworks,
instrumenting http requests served by applications utilizing the framework.

auto-instrumentation using the opentelemetry-instrumentation package is also supported.

Installation
------------

::

    pip install opentelemetry-instrumentation-fastapi

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

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
