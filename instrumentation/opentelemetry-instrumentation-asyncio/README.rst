OpenTelemetry asyncio Instrumentation
===========================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-asyncio.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-asyncio/

AsyncioInstrumentor: Tracing Requests Made by the Asyncio Library

Primary Use Case:
-----------------
1. Performance and Error Monitoring:
The AsyncioInstrumentor tool offers significant advantages for developers and system administrators. It's designed to monitor real-time performance bottlenecks and catch exceptions within specific asynchronous tasks.

When It's Not Ideal to Use AsyncioInstrumentor:
------------------------------------------------
1. Frameworks with Built-in Instrumentation:
If you're utilizing a framework like aiohttp that already includes built-in instrumentation, you might not need this library. In such cases, leveraging the built-in tools of the framework is generally more beneficial than using external ones like AsyncioInstrumentor.

2. Libraries Lacking Instrumentation:
Should you employ a library that isn't inherently instrumented, AsyncioInstrumentor can step in to fill that gap.

3. Concerns about Overhead:
Tracing each task and future consistently can lead to added overhead. As a best practice, it's wise to enable tracing only when crucial, especially during the development stage.

Example
-------
.. code:: python

    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
    AsyncioInstrumentor().instrument()

    import asyncio

    async def main():
        await asyncio.create_task(asyncio.sleep(0.1))

    asyncio.run(main())

API
---



Installation
------------

::

    pip install opentelemetry-instrumentation-asyncio


References
----------

* `OpenTelemetry asyncio/ Tracing <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/<REPLACE ME>/<REPLACE ME>.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
