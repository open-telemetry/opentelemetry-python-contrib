OpenTelemetry Anthropic Agents Instrumentation
==============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-anthropic-agents.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-anthropic-agents/

This library allows tracing LLM requests made by the
`Anthropic Python SDK <https://pypi.org/project/anthropic/>`_ Agents.

Installation
------------

::

    pip install opentelemetry-instrumentation-anthropic-agents

If you don't have an Anthropic application yet, try our `examples <examples>`_
which only need a valid Anthropic API key.

Check out the `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up Anthropic Agents instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

.. code-block:: python

    from opentelemetry.instrumentation.anthropic_agents import AnthropicAgentsInstrumentor
    import anthropic

    # Instrument Anthropic
    AnthropicAgentsInstrumentor().instrument()

    # Use Anthropic client as normal
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "Hello, Claude!"}
        ]
    )


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
* `Anthropic Documentation <https://docs.anthropic.com/>`_
