OpenTelemetry Redis Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-redis.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-redis/

This library allows tracing requests made by the Redis library.

Installation
------------

::

    pip install opentelemetry-instrumentation-redis

Semantic Conventions
--------------------

When the ``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable is set to
``database`` or ``database/dup``, the ``db.namespace`` attribute is set to the
Redis database index (as a string) configured when the connection was
established. For example, the default Redis database index ``0`` is emitted as
``db.namespace = "0"``.

References
----------

* `OpenTelemetry Redis Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
