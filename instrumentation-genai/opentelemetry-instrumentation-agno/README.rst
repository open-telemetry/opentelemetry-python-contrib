OpenTelemetry Agno Instrumentation
==================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-agno.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-agno/

This library allows tracing requests made by the Agno library.

Installation
------------

::

    pip install opentelemetry-instrumentation-agno

References
----------

* `OpenTelemetry Agno Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/agno/agno.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Agno <https://docs.agno.com/>`_

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.agno import AgnoInstrumentor
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    # Instrument Agno
    AgnoInstrumentor().instrument()

    # Create an agent
    agent = Agent(
        name="Assistant",
        model=OpenAIChat(id="gpt-4"),
        instructions="You are a helpful assistant."
    )

    # Run the agent
    result = agent.run("Hello, how are you?")

    print(result.content)

Configuration
-------------

Content Capture
~~~~~~~~~~~~~~~

By default, message content is not captured. To enable content capture, set the
environment variable:

.. code-block:: bash

    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true

Span Hierarchy
--------------

The instrumentation creates the following span hierarchy:

::

    {team_name}.team (Team.run/arun)
    └── {agent_name}.agent (Agent.run/arun)
        └── {tool_name}.tool (FunctionCall.execute/aexecute)

Attributes
----------

All custom attributes follow the ``gen_ai.agno.*`` namespace:

Agent Attributes
~~~~~~~~~~~~~~~~

* ``gen_ai.agno.agent.name`` - Agent name
* ``gen_ai.agno.entity.input`` - Input message (when content capture enabled)
* ``gen_ai.agno.entity.output`` - Output message (when content capture enabled)
* ``gen_ai.agno.run.id`` - Run ID

Team Attributes
~~~~~~~~~~~~~~~

* ``gen_ai.agno.team.name`` - Team name

Tool Attributes
~~~~~~~~~~~~~~~

* ``gen_ai.agno.tool.name`` - Tool/function name
* ``gen_ai.agno.tool.description`` - Tool description
* ``gen_ai.agno.tool.input`` - Tool input (when content capture enabled)
* ``gen_ai.agno.tool.output`` - Tool output (when content capture enabled)

Metrics
-------

The instrumentation records the following metrics:

* ``gen_ai.client.operation.duration`` - Duration of GenAI operations (seconds)
* ``gen_ai.client.token.usage`` - Number of tokens used

Streaming Support
-----------------

The instrumentation fully supports streaming responses. When streaming is enabled,
the span is kept open until the stream is fully consumed, at which point metrics
and output attributes are recorded.

API
---
