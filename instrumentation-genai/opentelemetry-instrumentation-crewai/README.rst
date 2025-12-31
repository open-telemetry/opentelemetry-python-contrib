OpenTelemetry CrewAI Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-crewai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-crewai/

This library allows tracing requests made by the CrewAI library.

Installation
------------

::

    pip install opentelemetry-instrumentation-crewai

References
----------

* `OpenTelemetry CrewAI Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/crewai/crewai.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `CrewAI <https://docs.crewai.com/>`_

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
    from crewai import Agent, Task, Crew

    # Instrument CrewAI
    CrewAIInstrumentor().instrument()

    # Define your agents
    researcher = Agent(
        role="Researcher",
        goal="Research and provide accurate information",
        backstory="You are an experienced researcher with attention to detail."
    )

    writer = Agent(
        role="Writer",
        goal="Write compelling content based on research",
        backstory="You are a skilled writer who creates engaging content."
    )

    # Define tasks
    research_task = Task(
        description="Research the latest trends in AI",
        expected_output="A comprehensive report on AI trends",
        agent=researcher
    )

    write_task = Task(
        description="Write an article based on the research",
        expected_output="A well-written article",
        agent=writer
    )

    # Create and run the crew
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task]
    )

    result = crew.kickoff()

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

    crewai.workflow (Crew.kickoff)
    ├── {agent_role}.agent (Agent.execute_task)
    │   └── {task_description}.task (Task.execute_sync)
    │       └── {model}.llm (LLM.call)
    └── {agent_role}.agent
        └── ...

Attributes
----------

All custom attributes follow the ``gen_ai.crewai.*`` namespace:

Crew Attributes
~~~~~~~~~~~~~~~

* ``gen_ai.crewai.crew.tasks`` - JSON representation of crew tasks
* ``gen_ai.crewai.crew.agents`` - JSON representation of crew agents
* ``gen_ai.crewai.crew.result`` - Crew execution result

Agent Attributes
~~~~~~~~~~~~~~~~

* ``gen_ai.crewai.agent.role`` - Agent role
* ``gen_ai.crewai.agent.goal`` - Agent goal
* ``gen_ai.crewai.agent.backstory`` - Agent backstory
* ``gen_ai.crewai.agent.tools`` - Available tools
* ``gen_ai.crewai.agent.max_iter`` - Maximum iterations
* ``gen_ai.crewai.agent.allow_delegation`` - Whether delegation is allowed

Task Attributes
~~~~~~~~~~~~~~~

* ``gen_ai.crewai.task.description`` - Task description
* ``gen_ai.crewai.task.expected_output`` - Expected output
* ``gen_ai.crewai.task.agent`` - Assigned agent role
* ``gen_ai.crewai.task.async_execution`` - Whether async execution is enabled

Metrics
-------

The instrumentation records the following metrics:

* ``gen_ai.client.operation.duration`` - Duration of GenAI operations (seconds)
* ``gen_ai.client.token.usage`` - Number of tokens used

API
---
