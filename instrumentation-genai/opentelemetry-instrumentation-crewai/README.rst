OpenTelemetry CrewAI Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-crewai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-crewai/

This library instruments `CrewAI <https://pypi.org/project/crewai/>`_, a
framework for orchestrating multi-agent LLM workflows. It produces one
``invoke_workflow`` span per crew run, one ``invoke_agent`` span per
agent/task pair, and ``chat``/``execute_tool`` spans for every LLM call and
tool call an agent makes along the way.

When one agent's task output feeds into another agent's task, that handoff
is represented as an OpenTelemetry span **link** between the two agent
invocations, not as a parent-child relationship -- the two agents ran one
after another, not one inside the other, and nesting them would say
something that isn't true about the timeline.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-crewai

If you don't have a CrewAI application yet, try our `examples <examples>`_,
which only need a valid LLM provider API key.

Check out `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up CrewAI instrumentation if you're
setting OpenTelemetry up manually. Check out the
`manual example <examples/manual>`_ for more details.

.. code-block:: python

    from crewai import Agent, Crew, Task
    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()

    crew = Crew(agents=[...], tasks=[...])
    crew.kickoff()

Enabling message content
*************************

Prompt text, response text, and tool call arguments/results are not
captured by default -- only shapes and numbers (model name, token counts,
tool name, whether it errored). To capture message content, two settings
have to be enabled together:

- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` set to
  ``span_only``, ``event_only``, or ``span_and_event``.
- ``OTEL_SEMCONV_STABILITY_OPT_IN`` set to ``gen_ai_latest_experimental``
  (see below). Without it, message content is not captured regardless of
  the setting above -- this instrumentation stays on the stable v1.30.0
  semantic conventions, which do not carry message content.

Tool call arguments and results are the one exception: they're gated only
by ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` (any truthy
value, including plain ``true``), independent of the experimental opt-in.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

Enabling the latest experimental features
*******************************************

To enable the latest experimental features, including message content
capture, set the environment variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to
``gen_ai_latest_experimental``.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()
    # ...

    CrewAIInstrumentor().uninstrument()

References
----------
* `signoz#11663 <https://github.com/SigNoz/signoz/issues/11663>`_ -- the request this instrumentation was built against
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
