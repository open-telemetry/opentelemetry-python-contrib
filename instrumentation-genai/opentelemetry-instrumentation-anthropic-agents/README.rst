OpenTelemetry Anthropic Agents Instrumentation
==============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-anthropic-agents.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-anthropic-agents/

This library allows tracing LLM requests made by the
`Claude Agent SDK <https://github.com/anthropics/claude-agent-sdk-python>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-anthropic-agents

If you don't have a Claude Agent SDK application yet, try our `examples <examples>`_
which only need a valid Anthropic API key.

Check out the `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up Anthropic Agents instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

.. code-block:: python

    from opentelemetry.instrumentation.anthropic_agents import AnthropicAgentsInstrumentor
    from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition, AssistantMessage, TextBlock, query

    # Instrument Anthropic Agents
    AnthropicAgentsInstrumentor().instrument()

    # Use Claude Agent SDK as normal
    import anyio

    async def main():
        options = ClaudeAgentOptions(
            agents={
                "assistant": AgentDefinition(
                    description="A helpful assistant",
                    prompt="You are a helpful assistant.",
                    tools=["Read"],
                    model="sonnet",
                ),
            },
        )

        async for message in query(
            prompt="Hello, Claude!",
            options=options,
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

    anyio.run(main)


Configuration
-------------

Capture Message Content
***********************

By default, prompts and completions are not captured. To enable message content capture,
set the environment variable:

::

    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Claude Agent SDK (Python) <https://github.com/anthropics/claude-agent-sdk-python>`_
* `Anthropic Documentation <https://docs.anthropic.com/>`_
