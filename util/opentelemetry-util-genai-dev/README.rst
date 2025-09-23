OpenTelemetry GenAI Utilities (opentelemetry-util-genai)
========================================================

.. contents:: Table of Contents
   :depth: 2
   :local:
   :backlinks: entry

Overview
--------
This package supplies foundational data types, helper logic, and lifecycle utilities for emitting OpenTelemetry signals around Generative AI (GenAI) model invocations.

Primary audiences:

* Instrumentation authors (framework / model provider wrappers)
* Advanced users building custom GenAI telemetry capture pipelines
* Early adopters validating incubating GenAI semantic conventions (semconv)

The current focus is the span lifecycle and (optionally) message content capture. Metric & event enriched generators exist in experimental form and may stabilize later.

High-Level Architecture
-----------------------
::

    Application / Model SDK
        -> Build LLMInvocation (request model, messages, attributes)
        -> TelemetryHandler.start_llm(invocation)
        -> Execute provider call (obtain output, tokens, metadata)
        -> Populate invocation.output_messages / token counts / extra attributes
        -> TelemetryHandler.stop_llm(invocation)  (or fail_llm on error)
        -> OpenTelemetry exporter sends spans (and optionally metrics / events)

Future / optional enrichment paths:

* Metrics (token counts, durations) via metric-capable generators
* Structured log events for input details & per-choice completions

Core Concepts
-------------
* **LLMInvocation**: Mutable container representing a logical model call (request through response lifecycle).
* **Messages** (``InputMessage`` / ``OutputMessage``): Chat style role + parts (``Text``, ``ToolCall``, ``ToolCallResponse`` or arbitrary future part types).
* **ContentCapturingMode**: Enum controlling whether message content is recorded in spans, events, both, or not at all.
* **TelemetryHandler**: High-level façade orchestrating start / stop / fail operations using a chosen generator.
* **Generators**: Strategy classes translating invocations into OpenTelemetry signals.

Current Generator Variants (see ``generators/`` README for deep detail):

* ``SpanGenerator`` (default): spans only + optional input/output message attributes.
* ``SpanMetricGenerator``: spans + metrics (duration, tokens) + optional input/output message attributes
* ``SpanMetricEventGenerator``: spans + metrics + structured log events.

.. note:: See detailed generator strategy documentation in ``src/opentelemetry/util/genai/generators/README.rst``.

Data Model Summary
------------------
Attributes follow incubating GenAI semantic conventions (subject to change). Key attributes (when enabled):

* ``gen_ai.operation.name = "chat"``
* ``gen_ai.request.model``
* ``gen_ai.response.model`` (when provider response model differs)
* ``gen_ai.provider.name``
* ``gen_ai.input.messages`` (JSON array as string; gated by content capture)
* ``gen_ai.output.messages`` (JSON array as string; gated by content capture)
* ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens`` (future metric integration)

Lifecycle API
-------------
1. Construct ``LLMInvocation``
2. ``handler.start_llm(invocation)``
3. Perform model request
4. Populate ``invocation.output_messages`` (+ tokens / response IDs / extra attrs)
5. ``handler.stop_llm(invocation)`` or ``handler.fail_llm(invocation, Error)``

Public Types (abridged)
-----------------------
* ``class LLMInvocation``
  * ``request_model: str`` (required)
  * ``provider: Optional[str]``
  * ``input_messages: list[InputMessage]``
  * ``output_messages: list[OutputMessage]``
  * ``attributes: dict[str, Any]`` (arbitrary span attributes)
  * ``input_tokens`` / ``output_tokens`` (Optional[int | float])
* ``class InputMessage(role: str, parts: list[MessagePart])``
* ``class OutputMessage(role: str, parts: list[MessagePart], finish_reason: str)``
* ``class Text(content: str)``
* ``class ToolCall`` / ``ToolCallResponse``
* ``class Error(message: str, type: Type[BaseException])``
* ``enum ContentCapturingMode``: ``NO_CONTENT`` | ``SPAN_ONLY`` | ``EVENT_ONLY`` | ``SPAN_AND_EVENT``

TelemetryHandler
----------------
Entry point helper (singleton via ``get_telemetry_handler``). Responsibilities:

* Selects generator (currently ``SpanGenerator``) & configures capture behavior
* Applies semantic convention schema URL
* Shields instrumentation code from direct span manipulation

Example Usage
-------------
.. code-block:: python

   from opentelemetry.util.genai.handler import get_telemetry_handler
   from opentelemetry.util.genai.types import (
       LLMInvocation, InputMessage, OutputMessage, Text
   )

   handler = get_telemetry_handler()

   invocation = LLMInvocation(
       request_model="gpt-4o-mini",
       provider="openai",
       input_messages=[InputMessage(role="user", parts=[Text(content="Hello, world")])],
       attributes={"custom_attr": "demo"},
   )

   handler.start_llm(invocation)
   # ... perform provider call ...
   invocation.output_messages = [
       OutputMessage(role="assistant", parts=[Text(content="Hi there!")], finish_reason="stop")
   ]
   invocation.attributes["scenario"] = "basic-greeting"
   handler.stop_llm(invocation)

Error Flow Example
------------------
.. code-block:: python

   from opentelemetry.util.genai.types import Error

   try:
       handler.start_llm(invocation)
       # provider call that may raise
   except Exception as exc:  # noqa: BLE001 (example)
       handler.fail_llm(invocation, Error(message=str(exc), type=exc.__class__))
       raise

Configuration & Environment Variables
-------------------------------------
Content capture requires *experimental* GenAI semconv mode + explicit env var.

1. Enable experimental semconv:

   ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``

2. Select content capture mode:

   ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=<MODE>``

   Accepted values: ``NO_CONTENT`` (default), ``SPAN_ONLY``, ``EVENT_ONLY``, ``SPAN_AND_EVENT``.

3. (NEW) Select telemetry generator flavor:

   ``OTEL_INSTRUMENTATION_GENAI_GENERATOR=<FLAVOR>``

   Accepted values (case-insensitive):

   * ``span`` (default) – spans only.
   * ``span_metric`` – spans + metrics.
   * ``span_metric_event`` – spans + metrics + structured log events (no message content on spans).

Flavor vs Artifact Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~
+---------------------+----------------------+-----------------------------+-------------------+---------------------------------------------+
| Flavor              | Spans                | Metrics (duration/tokens)   | Events / Logs      | Where message content can appear            |
+=====================+======================+=============================+===================+=============================================+
| span                | Yes                  | No                          | No                | Span attrs if mode=SPAN_ONLY/SPAN_AND_EVENT |
+---------------------+----------------------+-----------------------------+-------------------+---------------------------------------------+
| span_metric         | Yes                  | Yes                         | No                | Span attrs if mode=SPAN_ONLY/SPAN_AND_EVENT |
+---------------------+----------------------+-----------------------------+-------------------+---------------------------------------------+
| span_metric_event   | Yes (no msg content) | Yes                         | Yes (structured)  | Events only if mode=EVENT_ONLY/SPAN_AND_EVENT |
+---------------------+----------------------+-----------------------------+-------------------+---------------------------------------------+

Content Capture Interplay Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``NO_CONTENT``: No message bodies recorded anywhere (spans/events) regardless of flavor.
* ``SPAN_ONLY``: Applies only to ``span`` / ``span_metric`` flavors (messages serialized onto span attributes). Ignored for ``span_metric_event`` (treated as ``NO_CONTENT`` there).
* ``EVENT_ONLY``: Applies only to ``span_metric_event`` (message bodies included in events). For other flavors behaves like ``NO_CONTENT``.
* ``SPAN_AND_EVENT``: For ``span`` / ``span_metric`` behaves like ``SPAN_ONLY`` (events are not produced). For ``span_metric_event`` behaves like ``EVENT_ONLY`` (messages only in events to avoid duplication).

Generator Selection
-------------------
The handler now supports explicit generator selection via environment variable (see above). If an invalid value is supplied it falls back to ``span``.

Previously this section noted future enhancements; the selection mechanism is now implemented.

Extensibility
-------------
Subclass ``BaseTelemetryGenerator``:

.. code-block:: python

   from opentelemetry.util.genai.generators import BaseTelemetryGenerator
   from opentelemetry.util.genai.types import LLMInvocation, Error

   class CustomGenerator(BaseTelemetryGenerator):
       def start(self, invocation: LLMInvocation) -> None:
           ...
       def finish(self, invocation: LLMInvocation) -> None:
           ...
       def error(self, error: Error, invocation: LLMInvocation) -> None:
           ...

Inject your custom generator in a bespoke handler or fork the existing ``TelemetryHandler``.

Evaluation Integration
~~~~~~~~~~~~~~~~~~~~~~
You can integrate external evaluation packages to measure and annotate LLM invocations without modifying the core GenAI utilities. Evaluators implement the ``Evaluator`` interface, register themselves with the handler registry, and are dynamically loaded at runtime via environment variables.

Example: deepeval integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The `deepeval` package provides a rich suite of LLM quality metrics (relevance, bias, hallucination, toxicity, etc.). To install and enable the deepeval evaluator:

.. code-block:: bash

   # Install the core utilities with deepeval support
   pip install opentelemetry-util-genai[deepeval]

   # Enable evaluation and select the deepeval evaluator
   export OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE=true
   export OTEL_INSTRUMENTATION_GENAI_EVALUATORS=deepeval

At runtime, after you start and stop your LLM invocation, call:

.. code-block:: python

   from opentelemetry.util.genai.handler import get_telemetry_handler

   handler = get_telemetry_handler()
   # ... run your invocation lifecycle (start_llm, provider call, stop_llm) ...
   results = handler.evaluate_llm(invocation)
   for eval_result in results:
       print(f"{eval_result.metric_name}: {eval_result.score} ({eval_result.label})")

Beyond deepeval, you can create or install other evaluator packages by implementing the ``Evaluator`` interface and registering with the GenAI utilities registry. The handler will load any evaluators listed in ``OTEL_INSTRUMENTATION_GENAI_EVALUATORS``.

Threading / Concurrency
-----------------------
* A singleton handler is typical; OpenTelemetry SDK manages concurrency.
* Do **not** reuse an ``LLMInvocation`` instance across requests.

Stability Disclaimer
--------------------
GenAI semantic conventions are incubating; attribute names & enabling conditions may change. Track the project CHANGELOG & release notes.

Troubleshooting
---------------
* **Span missing message content**:
  * Ensure experimental stability + capture env var set *before* ``start_llm``.
  * Verify messages placed in ``input_messages``.
* **No spans exported**:
  * Confirm a ``TracerProvider`` is configured and set globally.

Roadmap (Indicative)
--------------------
* Configurable generator selection (env / handler param)
* Metrics stabilization (token counts & durations) via ``SpanMetricGenerator``
* Event emission (choice logs) maturity & stabilization
* Enhanced tool call structured representation

Minimal End-to-End Test Snippet
--------------------------------
.. code-block:: python

   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import SimpleSpanProcessor, InMemorySpanExporter
   from opentelemetry import trace

   exporter = InMemorySpanExporter()
   provider = TracerProvider()
   provider.add_span_processor(SimpleSpanProcessor(exporter))
   trace.set_tracer_provider(provider)

   from opentelemetry.util.genai.handler import get_telemetry_handler
   from opentelemetry.util.genai.types import LLMInvocation, InputMessage, OutputMessage, Text

   handler = get_telemetry_handler()
   inv = LLMInvocation(
       request_model="demo-model",
       provider="demo-provider",
       input_messages=[InputMessage(role="user", parts=[Text(content="ping")])],
   )
   handler.start_llm(inv)
   inv.output_messages = [OutputMessage(role="assistant", parts=[Text(content="pong")], finish_reason="stop")]
   handler.stop_llm(inv)

   spans = exporter.get_finished_spans()
   assert spans and spans[0].name == "chat demo-model"

License
-------
See parent repository LICENSE (Apache 2.0 unless otherwise stated).
