OpenTelemetry MCP Instrumentation
==================================

OpenTelemetry instrumentation for Model Context Protocol (MCP).

Installation
------------

.. code-block:: bash

    pip install opentelemetry-instrumentation-mcp

Usage
-----

Automatically enabled with:

.. code-block:: bash

    opentelemetry-instrument python your_mcp_app.py

Examples
--------

See the ``examples/`` directory for complete working examples:

- **simple-client-server**: stdio transport example with Jaeger integration
- **http-transport**: HTTP/SSE transport example with console exporter

Supported Transports
--------------------

- **stdio**: Process-based communication (stdin/stdout)
- **HTTP/SSE**: Network-based communication with Server-Sent Events

Both transports are fully instrumented with automatic trace context propagation.

Spans Created
-------------

- **Client spans**: ``mcp.client`` with method-specific names (e.g., ``tools/call add``)
- **Server spans**: ``mcp.server`` with method-specific names
- Distributed tracing via W3C trace context in message metadata