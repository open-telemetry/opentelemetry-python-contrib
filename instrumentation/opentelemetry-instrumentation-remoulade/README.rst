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

Usage
-----

* Start broker backend

::

    docker run -p 5672:5672 rabbitmq

* Run instrumented actor

.. code-block:: python

    from remoulade.brokers.rabbitmq import RabbitmqBroker
    import remoulade

    broker = RabbitmqBroker()
    remoulade.set_broker(broker)

    RemouladeInstrumentor().instrument()

    @remoulade.actor
    def multiply(x, y):
        return x * y

    broker.declare_actor(count_words)

    multiply.send(43, 51)


Setting up tracing
--------------------
    The ``instrument()`` method of the RemouladeInstrumentor should always be called after the broker is set, because the instrumentation is attached to the broker.



References
----------

* `OpenTelemetry Redis Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
