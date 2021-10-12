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

Configuration
-------------

Request/Response hooks
**********************

Utilize request/reponse hooks to execute custom logic to be performed before/after performing a request. Instance is of type redis.connection.Connection.

.. code-block:: python

    def request_hook(span, instance, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span, instance, response):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    RedisInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook)

References
----------

* `OpenTelemetry Redis Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/opentelemetry-instrumentation-redis/opentelemetry-instrumentation-redis.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
