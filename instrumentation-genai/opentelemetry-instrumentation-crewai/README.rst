OpenTelemetry CrewAI Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-crewai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-crewai/

This library allows tracing multi-agent workflows built with the
`CrewAI <https://pypi.org/project/crewai/>`_ framework.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``) and is produced through the shared ``opentelemetry-util-genai``
telemetry handler. The instrumentation emits:

- an ``invoke_workflow`` span for each ``Crew.kickoff`` / ``Crew.kickoff_async``,
- an ``invoke_agent`` span for each ``Agent.execute_task`` (with
  ``gen_ai.provider.name = crewai``, ``gen_ai.agent.name`` set to the agent's
  role, and ``gen_ai.request.model`` set to the agent's configured LLM model),
- an ``execute_tool`` span for each tool execution (``BaseTool.run``).

The underlying LLM call (``crewai.llm.LLM.call``) is intentionally **not**
wrapped by this instrumentation to avoid double-instrumenting the underlying
model provider. To capture chat/inference spans, instrument the provider SDK
(or LiteLLM) directly.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-crewai

Usage
-----

.. code-block:: python

    from crewai import Agent, Crew, Task
    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()

    crew = Crew(agents=[...], tasks=[...])
    result = crew.kickoff()

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the CrewAI instrumentation is a no-op** (a legacy
Semantic Conventions v1.30.0 path is not yet provided).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function
arguments and return values are not captured by default. To capture message
content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()
    # ...

    # Uninstrument
    CrewAIInstrumentor().uninstrument()

Follow-ups / known gaps
-----------------------

- Only span attributes available at the wrapper boundary are set today
  (workflow name, agent role/model, tool name). Token usage, finish reasons,
  and message content extraction from CrewAI internals are not yet populated.

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `CrewAI <https://pypi.org/project/crewai/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
