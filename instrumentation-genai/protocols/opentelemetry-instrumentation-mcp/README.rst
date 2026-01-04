OpenTelemetry MCP (Model Context Protocol) Instrumentation
===========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-mcp.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-mcp/

This library allows tracing MCP (Model Context Protocol) operations using the
`MCP Python SDK <https://pypi.org/project/mcp/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-mcp

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.mcp import MCPInstrumentor
    from mcp import ClientSession

    # Instrument MCP
    MCPInstrumentor().instrument()

    # Use MCP client as normal
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        result = await session.call_tool("my_tool", arguments={"arg": "value"})

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
