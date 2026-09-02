OpenTelemetry HTTPX Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-httpx.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-httpx/

This library allows tracing HTTP requests made by the
`httpx <https://www.python-httpx.org/>`_ and
`httpx2 <https://httpx2.pydantic.dev/>`_ libraries.

If both libraries are installed, use ``HTTPXClientInstrumentor`` for
``httpx`` clients and ``HTTPX2ClientInstrumentor`` for ``httpx2`` clients.
The instrumentors can be enabled independently.

Installation
------------

::

     pip install opentelemetry-instrumentation-httpx


Usage
-----

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace requests.

.. code-block:: python

    import httpx
    import asyncio
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    url = "https://example.com"
    HTTPXClientInstrumentor().instrument()

    with httpx.Client() as client:
        response = client.get(url)

    async def get(url):
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

    asyncio.run(get(url))

The same package also supports `httpx2 <https://httpx2.pydantic.dev/>`_ using
the ``HTTPX2ClientInstrumentor``:

.. code-block:: python

    import httpx2
    import asyncio
    from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor

    url = "https://example.com"
    HTTPX2ClientInstrumentor().instrument()

    with httpx2.Client() as client:
        response = client.get(url)

    async def get(url):
        async with httpx2.AsyncClient() as client:
            response = await client.get(url)

    asyncio.run(get(url))


Instrumenting single clients
****************************

If you only want to instrument requests for specific client instances, you can
use the `HTTPXClientInstrumentor.instrument_client` method.


.. code-block:: python

    import httpx
    import asyncio
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    url = "https://example.com"

    with httpx.Client() as client:
        HTTPXClientInstrumentor.instrument_client(client)
        response = client.get(url)

    async def get(url):
        async with httpx.AsyncClient() as client:
            HTTPXClientInstrumentor.instrument_client(client)
            response = await client.get(url)

    asyncio.run(get(url))

For ``httpx2`` clients, use ``HTTPX2ClientInstrumentor.instrument_client``:

.. code-block:: python

    import httpx2
    from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor

    with httpx2.Client() as client:
        HTTPX2ClientInstrumentor.instrument_client(client)
        response = client.get("https://example.com")

Uninstrument
************

If you need to uninstrument clients, there are two options available.

.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()
    client = httpx.Client()

    # Uninstrument a specific client
    HTTPXClientInstrumentor.uninstrument_client(client)

    # Uninstrument all clients
    HTTPXClientInstrumentor().uninstrument()


Using transports directly
*************************

If you don't want to use the instrumentor class, you can use the transport classes directly.


.. code-block:: python

    import httpx
    import asyncio
    from opentelemetry.instrumentation.httpx import (
        AsyncOpenTelemetryTransport,
        SyncOpenTelemetryTransport,
    )

    url = "https://example.com"
    transport = httpx.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransport(transport)

    with httpx.Client(transport=telemetry_transport) as client:
        response = client.get(url)

    transport = httpx.AsyncHTTPTransport()
    telemetry_transport = AsyncOpenTelemetryTransport(transport)

    async def get(url):
        async with httpx.AsyncClient(transport=telemetry_transport) as client:
            response = await client.get(url)

    asyncio.run(get(url))

For ``httpx2`` transports, use ``SyncOpenTelemetryTransportHttpx2`` and
``AsyncOpenTelemetryTransportHttpx2``:

.. code-block:: python

    import httpx2
    from opentelemetry.instrumentation.httpx import SyncOpenTelemetryTransportHttpx2

    transport = httpx2.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransportHttpx2(transport)

    with httpx2.Client(transport=telemetry_transport) as client:
        response = client.get("https://example.com")


Request and response hooks
***************************

The instrumentation supports specifying request and response hooks. These are functions that get called back by the instrumentation right after a span is created for a request
and right before the span is finished while processing a response.

.. note::

    The request hook receives the raw arguments provided to the transport layer. The response hook receives the raw return values from the transport layer.

The hooks can be configured as follows:


.. code-block:: python

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    def request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    def response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    async def async_request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    async def async_response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    HTTPXClientInstrumentor().instrument(
        request_hook=request_hook,
        response_hook=response_hook,
        async_request_hook=async_request_hook,
        async_response_hook=async_response_hook
    )


Or if you are using the transport classes directly:


.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport

    def request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    def response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    async def async_request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    async def async_response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    transport = httpx.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransport(
        transport,
        request_hook=request_hook,
        response_hook=response_hook
    )

    async_transport = httpx.AsyncHTTPTransport()
    async_telemetry_transport = AsyncOpenTelemetryTransport(
        async_transport,
        request_hook=async_request_hook,
        response_hook=async_response_hook
    )

Logging response payloads
-------------------------

The ``response`` value passed to ``response_hook`` contains the response
stream. Reading that stream inside the hook consumes it before the application
can read the response body.

To inspect or log response payload chunks, wrap the HTTPX transport and yield
chunks from the response object instead of reading the hook's stream directly:

.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import SyncOpenTelemetryTransport

    class LoggingResponse(httpx.Response):
        def iter_bytes(self, *args, **kwargs):
            for chunk in super().iter_bytes(*args, **kwargs):
                print(chunk)
                yield chunk

    class LoggingTransport(httpx.BaseTransport):
        def __init__(self, transport):
            self._transport = transport

        def handle_request(self, request):
            response = self._transport.handle_request(request)
            return LoggingResponse(
                status_code=response.status_code,
                headers=response.headers,
                stream=response.stream,
                extensions=response.extensions,
            )

        def close(self):
            self._transport.close()

    def response_hook(span, request, response):
        status_code, headers, stream, extensions = response
        span.set_attribute("http.response.status_code", status_code)
        # Do not read stream here; LoggingResponse logs chunks safely.

    transport = LoggingTransport(httpx.HTTPTransport())
    telemetry_transport = SyncOpenTelemetryTransport(
        transport,
        response_hook=response_hook,
    )

    with httpx.Client(transport=telemetry_transport) as client:
        response = client.get("https://example.com")
        response.read()

For request payloads, prefer logging or redacting the body before it is passed
to HTTPX. Avoid recording secrets, credentials, or personally identifiable
information in span attributes or logs.


References
----------

* `OpenTelemetry HTTPX Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
