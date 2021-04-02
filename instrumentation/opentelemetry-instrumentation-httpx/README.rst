OpenTelemetry HTTPX Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-httpx.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-httpx/

This library allows tracing HTTP requests made by the
`httpx <https://www.python-httpx.org/>`_ library.

Installation
------------

::

     pip install opentelemetry-instrumentation-httpx


Usage
-----

Instrumenting all clients
*************************

When using the instrumentor, all newly created clients will automatically trace
requests.

.. code-block:: python

     import httpx
     from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

     url = "https://httpbin.org/get"
     HTTPXClientInstrumentor().instrument()

     with httpx.Client() as client:
          response = client.get(url)

     async with httpx.AsyncClient() as client:
          response = await client.get(url)

Uninstrument
^^^^^^^^^^^^

If you need to uninstrument clients, there are two options available.

.. code-block:: python

     import httpx
     from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

     HTTPXClientInstrumentor().instrument()
     client = httpx.Client()

     # Uninstrument a specific client
     HTTPXClientInstrumentor.uninstrument_client(client)
     
     # Uninstrument all new clients
     HTTPXClientInstrumentor().uninstrument()


Instrumenting single clients
****************************

If you only want to instrument requests for specific client instances, you can
create the transport instance manually and pass it in when creating the client.


.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import (
        AsyncOpenTelemetryTransport,
        SyncOpenTelemetryTransport,
    )

    url = "https://httpbin.org/get"
    transport = httpx.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransport(transport)

    with httpx.Client(transport=telemetry_transport) as client:
        response = client.get(url)

    transport = httpx.AsyncHTTPTransport()
    telemetry_transport = AsyncOpenTelemetryTransport(transport)

    async with httpx.AsyncClient(transport=telemetry_transport) as client:
        response = await client.get(url)


References
----------

* `OpenTelemetry HTTPX Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
