OpenTelemetry OpenAI Agents Instrumentation
===========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-openai-agents-v2.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-openai-agents-v2/

This library provides the official OpenTelemetry instrumentation for the
`openai-agents SDK <https://pypi.org/project/openai-agents/>`_. It converts
the rich trace data emitted by the Agents runtime
into the GenAI semantic conventions, enriches spans with request/response payload
metadata, and records duration/token usage metrics.

Features
--------

* Generates spans for agents, tools, generations, guardrails, and handoffs using
  the OpenTelemetry GenAI semantic conventions.
* Captures prompts, responses, tool arguments, and system instructions when content
  capture is enabled.
* Publishes duration and token metrics for every operation.
* Supports environment overrides so you can configure agent metadata or disable
  telemetry without code changes.

Installation
------------

If your application is already configured with OpenTelemetry, install the package
and its optional instruments:

.. code-block:: console

    pip install opentelemetry-instrumentation-openai-agents-v2
    pip install openai-agents

Usage
-----

Instrumentation automatically wires the Agents tracing processor into the SDK.
Configure OpenTelemetry as usual, then call :class:`OpenAIAgentsInstrumentor`.

.. code-block:: python

    from agents import Agent, Runner, function_tool
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor


    def configure_otel() -> None:
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


    @function_tool
    def get_weather(city: str) -> str:
        return f"The forecast for {city} is sunny with pleasant temperatures."


    assistant = Agent(
        name="Travel Concierge",
        instructions="You are a concise travel concierge.",
        tools=[get_weather],
    )

    result = Runner.run_sync(assistant, "I'm visiting Barcelona this weekend. How should I pack?")
    print(result.final_output)

Configuration
-------------

The instrumentor exposes runtime toggles through keyword arguments and environment
variables:

* ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` or
  ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT`` – controls how much
  message content is captured. Valid values map to
  :class:`opentelemetry.instrumentation.openai_agents.ContentCaptureMode`
  (``span_only``, ``event_only``, ``span_and_event``, ``no_content``).
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS`` – set to ``false`` to
  disable duration/token metrics.
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_SYSTEM`` – overrides the ``gen_ai.system``
  attribute when your deployment is not the default OpenAI platform.

You can also override agent metadata directly when calling
``OpenAIAgentsInstrumentor().instrument(...)`` using ``agent_name``, ``agent_id``,
``agent_description``, ``base_url``, ``server_address``, and ``server_port``.

Examples
--------

The :mod:`examples` directory contains runnable scenarios, including:

* ``examples/manual`` – manual OpenTelemetry configuration for a single agent run.
* ``examples/content-capture`` – demonstrates span and event content capture.
* ``examples/zero-code`` – end-to-end setup using environment configuration only.

References
----------

* `OpenTelemetry Python Contrib <https://github.com/open-telemetry/opentelemetry-python-contrib>`_
* `OpenTelemetry GenAI semantic conventions <https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/>`_
* `OpenAI Agents SDK <https://github.com/openai/openai-agents-python>`_
