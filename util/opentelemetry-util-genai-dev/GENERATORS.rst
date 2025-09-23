GenAI Telemetry Generators
==========================

This document describes strategy implementations ("generators") that translate a logical GenAI model
invocation (``LLMInvocation``) into OpenTelemetry signals.

Generator Matrix
----------------
The following summarizes capabilities (✅ = provided, ❌ = not provided; "Optional" = controlled by
content capture mode / configuration):

========================  =====  =======  ======================  =========================  ==================
Generator                 Spans  Metrics  Structured Log Events   Message Content Capture     Intended Stability
========================  =====  =======  ======================  =========================  ==================
SpanGenerator             ✅     ❌       ❌                       Optional (env+flag)        Default / earliest
SpanMetricGenerator       ✅     ✅       ❌                       Optional                  Experimental
SpanMetricEventGenerator  ✅     ✅       ✅ (choices & inputs)     Optional                  Experimental
========================  =====  =======  ======================  =========================  ==================

Note: Only ``SpanGenerator`` is presently wired by ``TelemetryHandler`` for general usage. Others are
available for iterative design and may evolve.

Common Concepts
---------------
All generators implement ``BaseTelemetryGenerator`` with the contract:

* ``start(invocation)`` – Prepare span (and context) at request dispatch time.
* ``finish(invocation)`` – Finalize span upon successful response.
* ``error(error, invocation)`` – Mark span with error status and finalize.

Shared data model (``../src/opentelemetry/util/genai/types.py``):

* ``LLMInvocation`` – mutable container instrumentation layers populate before/after provider calls.
* ``InputMessage`` / ``OutputMessage`` – chat-style messages.
* ``Text`` / ``ToolCall`` / ``ToolCallResponse`` – structured parts.

SpanGenerator
-------------
Lightweight implementation creating a single CLIENT span named::

    chat {request_model}

Attributes applied:

* ``gen_ai.operation.name = "chat"``
* ``gen_ai.request.model``
* ``gen_ai.provider.name`` (when provided)
* Custom keys from ``invocation.attributes``

Optional (env-controlled) content capture adds JSON-serialized arrays:

* ``gen_ai.input.messages``
* ``gen_ai.output.messages``

No metrics or log events are emitted.

When to use:

* Minimal overhead.
* Only need tracing of invocation success/failure and basic attribution.

SpanMetricGenerator (Experimental)
----------------------------------
Adds metrics to ``SpanGenerator`` responsibilities:

* Duration histogram (latency)
* Token usage histogram (input/output tokens)

Adds (when available):

* ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens``
* ``gen_ai.response.model`` / ``gen_ai.response.id``
* ``gen_ai.response.finish_reasons``

No structured log events.

When to use:

* Need aggregated latency & token metrics without per-choice logs.

SpanMetricEventGenerator (Experimental)
--------------------------------------
Superset: spans + metrics + structured log records.

Emits:

* Input detail events (if content captured)
* Choice events per output (index, finish_reason, partial content)

Best for analytics or auditing multi-choice completions.

Risks / Considerations:

* Higher signal volume (events + potential duplication)
* Attribute names may change (incubating semconv)

Content Capture Policy
----------------------
Environment variables:

* ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` (required for content capture)
* ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY|EVENT_ONLY|SPAN_AND_EVENT|NO_CONTENT``

Interpretation:

* ``SPAN_ONLY`` – spans contain messages; events omitted.
* ``EVENT_ONLY`` – event-capable generators emit events; spans omit messages.
* ``SPAN_AND_EVENT`` – both span attributes & events include message details.
* ``NO_CONTENT`` – no message bodies recorded.

``SpanGenerator`` ignores EVENT_ONLY (treats as NO_CONTENT). ``SpanMetricEventGenerator`` obeys all modes.

Extending Generators
--------------------
To build a custom variant (e.g., streaming tokens):

1. Subclass ``BaseTelemetryGenerator``.
2. Implement ``start`` / ``finish`` / ``error``.
3. Add interim update methods as needed.

Template::

    from opentelemetry.util.genai.generators import BaseTelemetryGenerator
    from opentelemetry.util.genai.types import LLMInvocation, Error
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    class StreamingSpanGenerator(BaseTelemetryGenerator):
        def __init__(self):
            self._tracer = trace.get_tracer(__name__)
        def start(self, invocation: LLMInvocation) -> None:
            span = self._tracer.start_span(f"chat {invocation.request_model}", kind=SpanKind.CLIENT)
            invocation.span = span
        def finish(self, invocation: LLMInvocation) -> None:
            if invocation.span:
                invocation.span.end()
        def error(self, error: Error, invocation: LLMInvocation) -> None:
            if invocation.span:
                invocation.span.record_exception(Exception(error.message))
                invocation.span.end()

Naming Conventions
------------------
* Span name: ``chat {request_model}``
* Message attributes: ``gen_ai.input.messages``, ``gen_ai.output.messages``
* Completion content (metrics/event variants): ``gen_ai.completion.{index}.content`` / ``gen_ai.completion.{index}.role``

Design Rationale
----------------
* Separation of concerns: choose appropriate telemetry cost envelope.
* Progressive enrichment: upgrade generator without changing call sites.
* Future-proof: experimental variants iterate independently of the default.

Migration Guidance
------------------
* Trace only: ``SpanGenerator``.
* Latency & tokens: ``SpanMetricGenerator``.
* Per-choice analytics / auditing: ``SpanMetricEventGenerator``.

Roadmap Items
-------------
* Configurable generator selection (handler param / env var)
* Additional operation types (embeddings, images, function calls)
* Streaming token increment events

Caveats
-------
* Experimental generators use incubating attributes – subject to rename/deprecation.
* Large messages can inflate span size – consider redaction or disabling capture.

Testing Notes
-------------
* Core tests exercise ``SpanGenerator`` (naming, attributes, parent/child context).
* Add targeted tests before depending heavily on experimental variants in production.

