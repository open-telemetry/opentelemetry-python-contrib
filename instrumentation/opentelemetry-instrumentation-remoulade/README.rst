OpenTelemetry Remoulade Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-remoulade.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-remoulade/

This library allows tracing requests made by the Remoulade library.

Installation
------------

::

    pip install opentelemetry-instrumentation-remoulade

Usage
-----

* Start broker backend

::

    docker run -p 5672:5672 rabbitmq

* Run instrumented actor

.. code-block:: python

    from remoulade.brokers.rabbitmq import RabbitmqBroker
    import remoulade

    RemouladeInstrumentor().instrument()

    broker = RabbitmqBroker()
    remoulade.set_broker(broker)

    @remoulade.actor
    def multiply(x, y):
        return x * y

    broker.declare_actor(count_words)

    multiply.send(43, 51)



References
----------

* `OpenTelemetry Remoulade Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/remoulade/remoulade.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
