OpenTelemetry Claude Agent SDK Manual Instrumentation Example
=============================================================

This example demonstrates how to manually instrument your Claude Agent SDK application
with OpenTelemetry tracing.

Prerequisites
-------------

Install the required packages:

.. code-block:: bash

    # First install the OpenTelemetry util-genai package from source
    pip install git+https://github.com/open-telemetry/opentelemetry-python-contrib.git#egg=opentelemetry-util-genai&subdirectory=util/opentelemetry-util-genai
    
    # Or if you have the source locally:
    # pip install /path/to/opentelemetry-python-contrib/util/opentelemetry-util-genai
    
    # Then install the main packages
    pip install opentelemetry-instrumentation-claude-agent-sdk
    pip install claude-agent-sdk
    pip install opentelemetry-exporter-otlp

Configuration
-------------

Set up your environment variables for Alibaba Cloud DashScope:

.. code-block:: bash

    export ANTHROPIC_BASE_URL="https://dashscope.aliyuncs.com/apps/anthropic"
    export ANTHROPIC_API_KEY="your-api-key"
    export DASHSCOPE_API_KEY="your-dashscope-api-key"

Basic Usage
-----------

.. code-block:: python

    import asyncio
    import os
    from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
    from claude_agent_sdk import query, ClaudeAgentOptions

    # Apply instrumentation
    ClaudeAgentSDKInstrumentor().instrument()

    async def basic_example():
        """Simple Claude Agent query with tracing."""
        options = ClaudeAgentOptions(
            model="qwen-plus",  # Using Qwen model
            max_turns=3
        )
        
        async for message in query(
            prompt="What is the weather like today?",
            options=options
        ):
            print(f"Received: {type(message).__name__}")

    if __name__ == "__main__":
        asyncio.run(basic_example())

Advanced Usage with Tools
-------------------------

.. code-block:: python

    import asyncio
    from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
    from claude_agent_sdk import query, ClaudeAgentOptions

    # Apply instrumentation
    ClaudeAgentSDKInstrumentor().instrument()

    async def tool_example():
        """Example using tools with Claude Agent."""
        options = ClaudeAgentOptions(
            model="qwen-plus",
            allowed_tools=["Read", "Write"],
            system_prompt="You are a helpful assistant that can read and write files."
        )
        
        async for message in query(
            prompt="Create a file called 'hello.txt' with 'Hello, World!' in it",
            options=options
        ):
            print(f"Message: {type(message).__name__}")

    if __name__ == "__main__":
        asyncio.run(tool_example())

Exporting Traces
----------------

To export traces to an OTLP collector:

.. code-block:: bash

    export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
    export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
    python your_script.py

Or for HTTP protocol:

.. code-block:: bash

    export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
    export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://localhost:4318/v1/traces"
    python your_script.py

Viewing Traces
--------------

You can view the traces in various backends:

- **Console Exporter**: Set ``OTEL_TRACES_EXPORTER=console`` to see traces in stdout
- **Jaeger**: Use Jaeger UI at http://localhost:16686
- **Zipkin**: Use Zipkin UI at http://localhost:9411
- **Alibaba Cloud Managed Service for OpenTelemetry**: Configure with your cloud credentials

Task Tool Example
-----------------

.. code-block:: python

    import asyncio
    from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

    # Apply instrumentation
    ClaudeAgentSDKInstrumentor().instrument()

    async def task_example():
        """Example using Task tool for sub-agent delegation."""
        options = ClaudeAgentOptions(
            model="qwen-plus",
            system_prompt="You can delegate tasks to sub-agents when needed."
        )
        
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt="Research quantum computing and summarize key findings")
            async for message in client.receive_response():
                print(f"Response: {type(message).__name__}")

    if __name__ == "__main__":
        asyncio.run(task_example())