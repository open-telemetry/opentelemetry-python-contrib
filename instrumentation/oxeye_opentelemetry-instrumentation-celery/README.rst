oxeye_opentelemetry Celery Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-celery.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-celery/

Instrumentation for Celery.


Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-celery

Usage
-----

* Start broker backend

::
    docker run -p 5672:5672 rabbitmq


* Run instrumented task

.. code-block:: python

    from oxeye_opentelemetry import trace
    from oxeye_opentelemetry.sdk.trace import TracerProvider
    from oxeye_opentelemetry.sdk.trace.export import BatchSpanProcessor
    from oxeye_opentelemetry.instrumentation.celery import CeleryInstrumentor

    from celery import Celery
    from celery.signals import worker_process_init

    @worker_process_init.connect(weak=False)
    def init_celery_tracing(*args, **kwargs):
        trace.set_tracer_provider(TracerProvider())
        span_processor = BatchSpanProcessor(ConsoleSpanExporter())
        trace.get_tracer_provider().add_span_processor(span_processor)
        CeleryInstrumentor().instrument()

    app = Celery("tasks", broker="amqp://localhost")

    @app.task
    def add(x, y):
        return x + y

    add.delay(42, 50)


Setting up tracing 
--------------------

When tracing a celery worker process, tracing and instrumention both must be initialized after the celery worker
process is initialized. This is required for any tracing components that might use threading to work correctly
such as the BatchSpanProcessor. Celery provides a signal called ``worker_process_init`` that can be used to
accomplish this as shown in the example above.

References
----------
* `oxeye_opentelemetry Celery Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_

