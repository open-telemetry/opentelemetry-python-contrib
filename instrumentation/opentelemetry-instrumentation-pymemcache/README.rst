OpenTelemetry pymemcache Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-pymemcache.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-pymemcache/

Installation
------------

::

    pip install opentelemetry-instrumentation-pymemcache


Configuration
-------------

You can configure the semantic conventions emitted by this instrumentation via the ``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable:

- ``database`` - emit the new, stable db conventions, and stop emitting the old experimental db conventions that the instrumentation emitted previously.
- ``database/dup`` - emit both the old and the stable db conventions, allowing for a seamless transition.

By default, the old experimental db conventions are emitted.

References
----------
* `OpenTelemetry Pymemcache Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymemcache/pymemcache.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
