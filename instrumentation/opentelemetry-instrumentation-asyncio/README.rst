OpenTelemetry asyncio Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-asyncio.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-asyncio/

AsyncioInstrumentor: Tracing Requests Made by the Asyncio Library


The opentelemetry-instrumentation-asycnio package allows tracing asyncio applications.
The metric for coroutine, future, is generated even if there is no setting to generate a span.


Set the name of the coroutine you want to trace.
-------------------------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE=coro_name,coro_name2,coro_name3

If you want to keep track of which function to use in the to_thread function of asyncio, set the name of the function.
------------------------------------------------------------------------------------------------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE=func_name,func_name2,func_name3

For future, set it up like this
-----------------------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED=true

Run instrumented application
-----------------------------
1. coroutine
--------------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE=sleep

    import asyncio
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    AsyncioInstrumentor().instrument()

    async def main():
        await asyncio.create_task(asyncio.sleep(0.1))

    asyncio.run(main())

2. future
--------------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED=true

    loop = asyncio.get_event_loop()

    future = asyncio.Future()
    future.set_result(1)
    task = asyncio.ensure_future(future)
    loop.run_until_complete(task)

3. to_thread
--------------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE=func

    import asyncio
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    AsyncioInstrumentor().instrument()

    async def main():
        await asyncio.to_thread(func)

    def func():
        pass

    asyncio.run(main())


asyncio metric types
----------------------

* `asyncio.futures.duration` (ms) - Duration of the future
* `asyncio.futures.exceptions` (count) - Number of exceptions raised by the future
* `asyncio.futures.cancelled` (count) - Number of futures cancelled
* `asyncio.futures.created` (count) - Number of futures created
* `asyncio.futures.active` (count) - Number of futures active
* `asyncio.futures.finished` (count) - Number of futures finished
* `asyncio.futures.timeouts` (count) - Number of futures timed out

* `asyncio.coroutine.duration` (ms) - Duration of the coroutine
* `asyncio.coroutine.exceptions` (count) - Number of exceptions raised by the coroutine
* `asyncio.coroutine.created` (count) - Number of coroutines created
* `asyncio.coroutine.active` (count) - Number of coroutines active
* `asyncio.coroutine.finished` (count) - Number of coroutines finished
* `asyncio.coroutine.timeouts` (count) - Number of coroutines timed out
* `asyncio.coroutine.cancelled` (count) - Number of coroutines cancelled

* `asyncio.to_thread.duration` (ms) - Duration of the to_thread
* `asyncio.to_thread.exceptions` (count) - Number of exceptions raised by the to_thread
* `asyncio.to_thread.created` (count) - Number of to_thread created
* `asyncio.to_thread.active` (count) - Number of to_thread active
* `asyncio.to_thread.finished` (count) - Number of to_thread finished



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
