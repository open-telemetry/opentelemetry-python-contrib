OpenTelemetry Model Context Protocol (MCP) Instrumentation
==========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-mcp.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-mcp/

This library allows tracing client-side tool calls made through the
`Model Context Protocol Python SDK <https://pypi.org/project/mcp/>`_.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Each client-side ``ClientSession.call_tool`` invocation is
recorded as an ``execute_tool`` (tool-execution) span.

Scope and limitations
---------------------

This instrumentation currently emits **only client-side ``call_tool``
tool-execution spans**. The following are intentionally out of scope and are
planned as follow-up work:

- Transport / cross-process trace context propagation between the MCP client
  and server.
- ``ClientSession.list_tools`` and other MCP methods.
- The server-side ``ServerSession``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-mcp

Usage
-----

When using the instrumentor, all MCP client sessions will automatically trace
tool calls.

Make sure to configure OpenTelemetry tracing to capture all telemetry emitted
by the instrumentation.

.. code-block:: python

    from mcp.client.session import ClientSession
    from opentelemetry.instrumentation.mcp import McpInstrumentor

    McpInstrumentor().instrument()

    # ... open an MCP client session over a transport ...
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        result = await session.call_tool("get_weather", {"city": "London"})

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the MCP instrumentation is a no-op** (a legacy Semantic
Conventions v1.30.0 path is not yet provided).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Tool call arguments and results are not captured by default. To capture this
content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uploading tool arguments and results
*********************************

To enable the built-in upload hook, set:

- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload``
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` to an ``fsspec``-compatible URI/path
  (e.g. ``/path/to/prompts`` or ``gs://my_bucket``).

Install the ``upload`` extra to pull in ``fsspec``::

    pip install opentelemetry-util-genai[upload]

See the `opentelemetry-util-genai
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for additional options.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.mcp import McpInstrumentor

    McpInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    McpInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Model Context Protocol Python SDK <https://pypi.org/project/mcp/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
