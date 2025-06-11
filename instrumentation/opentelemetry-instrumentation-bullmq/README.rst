OpenTelemetry BullMQ Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-bullmq.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-bullmq/

This library allows tracing BullMQ job queue operations.

Installation
------------

::

    pip install opentelemetry-instrumentation-bullmq

Usage
-----

* Start Redis backend

.. code-block:: bash

    docker run -p 6379:6379 redis

* Run instrumented application

.. code-block:: python

    from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
    from bullmq import Queue, Worker
    
    # Instrument BullMQ
    BullMQInstrumentor().instrument()
    
    # Create queue and add job
    queue = Queue("myqueue")
    await queue.add("myjob", {"foo": "bar"})
    
    # Create worker to process jobs
    async def process_job(job):
        print(f"Processing job {job.id}: {job.data}")
        return "completed"
    
    worker = Worker("myqueue", process_job)
    await worker.run()

References
----------

* `OpenTelemetry BullMQ Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/bullmq/bullmq.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `BullMQ Python <https://github.com/taskforcesh/bullmq/tree/master/python>`_