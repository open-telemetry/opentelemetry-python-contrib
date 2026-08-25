OpenTelemetry Tortoise ORM Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-tortoiseorm.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-tortoiseorm/

This library allows tracing queries made by tortoise ORM backends, mysql, postgres and sqlite.

Installation
------------

::

     pip install opentelemetry-instrumentation-tortoiseorm

Configuration
-------------

You can configure the semantic conventions emitted by this instrumentation via the ``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable:

- ``database`` - emit the new, stable db conventions, and stop emitting the old experimental db conventions that the instrumentation emitted previously.
- ``database/dup`` - emit both the old and the stable db conventions, allowing for a seamless transition.

By default, the old experimental db conventions are emitted.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Tortoise ORM <https://tortoise.github.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
