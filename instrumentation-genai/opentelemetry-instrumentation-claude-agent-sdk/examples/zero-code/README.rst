OpenTelemetry Claude Agent SDK Zero-Code Instrumentation Example
================================================================

This example demonstrates how to instrument your Claude Agent SDK application
using the OpenTelemetry auto-instrumentation wrapper without code changes.

Prerequisites
-------------

Install the required packages:

.. code-block:: bash

    # First install the OpenTelemetry util-genai package from source
    pip install git+https://github.com/open-telemetry/opentelemetry-python-contrib.git#egg=opentelemetry-util-genai&subdirectory=util/opentelemetry-util-genai
    
    # Or if you have the source locally:
    # pip install /path/to/opentelemetry-python-contrib/util/opentelemetry-util-genai
    
    # Install OpenTelemetry packages (opentelemetry-distro is REQUIRED)
    pip install opentelemetry-distro
    pip install opentelemetry-exporter-otlp
    
    # Install Claude Agent SDK and instrumentation
    pip install claude-agent-sdk
    pip install opentelemetry-instrumentation-claude-agent-sdk

.. important::
    ``opentelemetry-distro`` is **required** for the ``opentelemetry-instrument`` 
    CLI to work properly. Without it, trace and metric exporters will not be 
    initialized correctly, and you will not see any telemetry output.

Configuration
-------------

Set up your environment variables for Alibaba Cloud DashScope:

.. code-block:: bash

    export ANTHROPIC_BASE_URL="https://dashscope.aliyuncs.com/apps/anthropic"
    export ANTHROPIC_API_KEY="your-api-key"
    export DASHSCOPE_API_KEY="your-dashscope-api-key"

Basic Usage
-----------

Create your application file (app.py):

.. code-block:: python

    import asyncio
    from claude_agent_sdk import query, ClaudeAgentOptions

    async def main():
        options = ClaudeAgentOptions(
            model="qwen-plus",
            max_turns=3
        )
        
        async for message in query(
            prompt="Explain quantum computing in simple terms",
            options=options
        ):
            print(f"Received: {type(message).__name__}")

    if __name__ == "__main__":
        asyncio.run(main())

Run with auto-instrumentation:

.. code-block:: bash

    opentelemetry-instrument \
        --traces_exporter console \
        --metrics_exporter console \
        python app.py

Exporting to OTLP Collector
---------------------------

To export to an OTLP collector:

.. code-block:: bash

    export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
    export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
    
    opentelemetry-instrument python app.py

Or for HTTP protocol:

.. code-block:: bash

    export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
    export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://localhost:4318/v1/traces"
    
    opentelemetry-instrument python app.py

Advanced Configuration
----------------------

You can configure various aspects of the instrumentation:

.. code-block:: bash

    # Set service name
    export OTEL_SERVICE_NAME="my-claude-agent-app"
    
    # Enable experimental GenAI semantic conventions
    export OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
    
    # Control message content capture
    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY
    
    # Run with instrumentation
    opentelemetry-instrument python app.py

Viewing Traces
--------------

With console exporter, traces will be printed to stdout. For visualization:

- **Jaeger**: Access at http://localhost:16686
- **Zipkin**: Access at http://localhost:9411
- **Alibaba Cloud**: Configure with your cloud credentials

Task Tool Support
-----------------

The instrumentation automatically tracks Task tool usage and sub-agent delegation:

.. code-block:: python

    import asyncio
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

    async def main():
        options = ClaudeAgentOptions(
            model="qwen-plus",
            system_prompt="You can delegate complex tasks to specialized sub-agents."
        )
        
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt="Research renewable energy technologies")
            async for message in client.receive_response():
                print(f"Response type: {type(message).__name__}")

    if __name__ == "__main__":
        asyncio.run(main())

Run with:

.. code-block:: bash

    opentelemetry-instrument python app.py