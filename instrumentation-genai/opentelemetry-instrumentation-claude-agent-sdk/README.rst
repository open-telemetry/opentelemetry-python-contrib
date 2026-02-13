OpenTelemetry Instrumentation for Claude Agent SDK
==================================================

This library provides automatic instrumentation for the `Claude Agent SDK
<https://github.com/anthropics/claude-agent-sdk-python>`_, adding OpenTelemetry
tracing and metrics for agent conversations, LLM calls, and tool executions.

.. note::
   This package is currently in development and must be installed from source.
   PyPI release is planned for future versions.

Installation
------------

::

    # Install OpenTelemetry core packages
    pip install opentelemetry-distro opentelemetry-exporter-otlp
    opentelemetry-bootstrap -a install

    # Install Claude Agent SDK
    pip install claude-agent-sdk

    # Install this instrumentation
    pip install opentelemetry-instrumentation-claude-agent-sdk

    # Note: This instrumentation uses ExtendedTelemetryHandler from opentelemetry-util-genai
    pip install ./util/opentelemetry-util-genai

.. important::
   ``opentelemetry-distro`` is **required** for auto-instrumentation with the 
   ``opentelemetry-instrument`` command. Without it, the CLI tool will not be 
   able to properly initialize trace exporters and providers.

Usage
-----

Auto-instrumentation
~~~~~~~~~~~~~~~~~~~~

Use the ``opentelemetry-instrument`` wrapper (requires ``opentelemetry-distro``):

::

    opentelemetry-instrument \
        --traces_exporter console \
        --metrics_exporter console \
        python your_claude_agent_app.py

Manual Instrumentation
~~~~~~~~~~~~~~~~~~~~~~

::

    from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
    from claude_agent_sdk import query
    from claude_agent_sdk.types import ClaudeAgentOptions

    ClaudeAgentSDKInstrumentor().instrument()

    options = ClaudeAgentOptions(model="claude-3-5-sonnet-20241022", max_turns=5)
    
    async def run_agent():
        async for message in query(prompt="Hello!", options=options):
            print(message)

    ClaudeAgentSDKInstrumentor().uninstrument()

Configuration
-------------

Export to OTLP Backend
~~~~~~~~~~~~~~~~~~~~~~

::

    export OTEL_SERVICE_NAME=my-claude-agent-app
    export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
    export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<trace_endpoint>
    export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=<metrics_endpoint>

    opentelemetry-instrument python your_app.py

Content Capture
~~~~~~~~~~~~~~~

Control message content capture using environment variables:

::

    # Enable experimental GenAI semantic conventions
    export OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental

    # Capture content in spans only
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY

    # Capture content in events only
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY

    # Capture in both spans and events
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_AND_EVENT

    # Disable content capture (default)
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT

Using with Alibaba Cloud DashScope
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This instrumentation works with Alibaba Cloud's DashScope service via the
Anthropic-compatible API endpoint:

::

    import os
    
    # Set environment variables for DashScope
    os.environ["ANTHROPIC_BASE_URL"] = "https://dashscope.aliyuncs.com/apps/anthropic"
    os.environ["ANTHROPIC_API_KEY"] = "your-dashscope-api-key"

Supported Components
--------------------

- **Agent Sessions**: ``query`` function for conversational agent interactions
- **Tool Executions**: Automatic tracing via message stream analysis
- **Token Tracking**: Via usage metadata in ResultMessage
- **Session Management**: Via SystemMessage session_id extraction

Visualization
-------------

Export telemetry data to:

- `Alibaba Cloud Managed Service for OpenTelemetry <https://www.aliyun.com/product/xtrace>`_
- Any OpenTelemetry-compatible backend (Jaeger, Zipkin, etc.)

Span Hierarchy
--------------

::

    invoke_agent (parent span)
      ├── User prompt event
      ├── execute_tool (child span)
      │   ├── gen_ai.tool.input.* attributes
      │   └── gen_ai.tool.response.* attributes
      ├── execute_tool (child span)
      │   └── ...
      └── Agent completed event

Examples
--------

See the examples directory for complete usage examples.

License
-------

Apache License 2.0

References
----------

- `OpenTelemetry GenAI Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/gen-ai/>`_
- `Claude Agent SDK <https://github.com/anthropics/claude-agent-sdk-python>`_
- `Alibaba Cloud DashScope Anthropic API <https://help.aliyun.com/zh/model-studio/anthropic-api-messages>`_

