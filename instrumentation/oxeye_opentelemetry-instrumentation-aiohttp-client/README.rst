oxeye_opentelemetry aiohttp client Integration
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-aiohttp-client.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-aiohttp-client/

This library allows tracing HTTP requests made by the
`aiohttp client <https://docs.aiohttp.org/en/stable/client.html>`_ library.

Installation
------------

::

     pip install oxeye_opentelemetry-instrumentation-aiohttp-client


Example
-------

.. code:: python

   import asyncio
   
   import aiohttp

   from oxeye_opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
   from oxeye_opentelemetry import trace
   from oxeye_opentelemetry.exporter.jaeger.thrift import JaegerExporter
   from oxeye_opentelemetry.sdk.trace import TracerProvider
   from oxeye_opentelemetry.sdk.trace.export import BatchSpanProcessor


   _JAEGER_EXPORTER = JaegerExporter(
      service_name="example-xxx",
      agent_host_name="localhost",
      agent_port=6831,
   )

   _TRACE_PROVIDER = TracerProvider()
   _TRACE_PROVIDER.add_span_processor(BatchSpanProcessor(_JAEGER_EXPORTER))
   trace.set_tracer_provider(_TRACE_PROVIDER)

   AioHttpClientInstrumentor().instrument()


   async def span_emitter():
      async with aiohttp.ClientSession() as session:
         async with session.get("https://example.com") as resp:
               print(resp.status)


   asyncio.run(span_emitter())


References
----------

* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `aiohttp client Tracing <https://docs.aiohttp.org/en/stable/tracing_reference.html>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
