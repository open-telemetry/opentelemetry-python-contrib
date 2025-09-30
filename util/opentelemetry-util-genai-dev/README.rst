OpenTelemetry GenAI Utilities (opentelemetry-util-genai)
========================================================

A lightweight, extensible toolkit for **observing Generative AI workloads** with OpenTelemetry.
It standardizes the lifecycle of LLM, embedding, and tool invocations; captures structured
content (when allowed); and supports pluggable, asynchronous **evaluation frameworks**.

.. contents:: Table of Contents
   :depth: 3
   :local:
   :backlinks: entry

Vision
------
Provide **zero/low–friction** primitives so instrumentation authors, platform teams, and
application developers can:

* Emit semantically consistent telemetry (spans, metrics, events/logs) for GenAI operations.
* Select the *shape* of telemetry via a single environment variable ("flavor").
* Defer expensive *evaluation* logic off the hot path (asynchronous sampling + background worker).
* Interoperate with existing ecosystems (e.g. Traceloop compatibility) without vendor lock‑in.
* Extend safely: add emitters, evaluators, upload hooks with minimal code.

High‑Level Architecture
-----------------------
Instrumentation (your code or an auto‑instrumentor) builds domain objects and delegates
lifecycle to a ``TelemetryHandler``. Emission is composed from small **emitters** managed by
a ``CompositeGenerator``. Evaluation is orchestrated separately by an ``EvaluationManager``.

::

   ┌──────────────┐    start_* / stop_*     ┌──────────────────┐
   │ Your Code /  │  ─────────────────────▶ │ TelemetryHandler │
   │ Instrumentor │ ◀────────────────────── │   (facade)       │
   └──────────────┘     spans / metrics /   └─────────┬────────┘
                               events                 │
                                                     ▼
                                         ┌────────────────────────┐
                                         │  CompositeGenerator    │
                                         │ (ordered emitters)     │
                                         └────────────────────────┘
                                                     │
                                          ┌──────────┴──────────┐
                                          │ Span / Metrics /    │
                                          │ Content / Traceloop │
                                          └──────────┬──────────┘
                                                     │
                                          ┌──────────┴──────────┐
                                          │ EvaluationManager   │
                                          │  (async sampling)   │
                                          └────────────��────────┘

Core Domain Types (``opentelemetry.util.genai.types``)
------------------------------------------------------
+-------------------------+--------------------------------------------------------------+
| Type                    | Purpose / Notes                                              |
+=========================+==============================================================+
| ``LLMInvocation``       | A single chat / completion style call. Input/output messages,|
|                         | tokens, provider, model, attributes, span ref.               |
+-------------------------+--------------------------------------------------------------+
| ``EmbeddingInvocation`` | Embedding model call (vectors intentionally *not* emitted).  |
+-------------------------+--------------------------------------------------------------+
| ``ToolCall``            | Structured function/tool invocation (duration focused).      |
+-------------------------+--------------------------------------------------------------+
| ``EvaluationResult``    | Output of a single evaluator metric (score, label, attrs).   |
+-------------------------+--------------------------------------------------------------+
| ``Error``               | Normalized error container (message + exception type).       |
+-------------------------+--------------------------------------------------------------+
| ``ContentCapturingMode``| Enum: NO_CONTENT / SPAN_ONLY / EVENT_ONLY / SPAN_AND_EVENT.  |
+-------------------------+--------------------------------------------------------------+

Design Pillars
--------------
1. **Separation of concerns** – Data classes hold data only; emitters interpret them.
2. **Composability** – Telemetry flavor = ordered set of emitters.
3. **Graceful opt‑in** – Heavy / optional dependencies imported lazily.
4. **Async evaluation** – Sampling & queueing is fast; analysis occurs off the critical path.
5. **Interoperability** – Traceloop compatibility emitter can run alone or alongside semconv emitters.
6. **Easily overridable** – Custom emitters/evaluators/queues can be introduced with minimal boilerplate.

Telemetry Handler
-----------------
``TelemetryHandler`` is the facade most users touch. Responsibilities:

* Parse environment once (flavor, content capture, evaluation enablement, intervals).
* Build the appropriate emitter pipeline (span / metrics / content events / traceloop).
* Provide typed lifecycle helpers (``start_llm``, ``stop_embedding`` …) plus generic ``start/finish/fail``.
* On ``stop_llm``: schedule asynchronous evaluations (sampling decision stored in invocation attributes).
* Optional immediate evaluation via ``evaluate_llm(invocation)`` (legacy / ad‑hoc path).

Emitters
--------
+----------------------------+--------------------------------------------------------------------------------------------------------------------------------+
| Emitter                    | Role                                                                                                                           |
+============================+================================================================================================================================+
| ``SpanEmitter``            | Creates & finalizes spans with semconv attributes. Optionally adds message content.                                            |
+----------------------------+--------------------------------------------------------------------------------------------------------------------------------+
| ``MetricsEmitter``         | Duration (all), token metrics (LLM only).                                                                                      |
+----------------------------+--------------------------------------------------------------------------------------------------------------------------------+
| ``ContentEventsEmitter``   | Structured events/log records for messages (LLM only) to keep spans lean.                                                      |
+----------------------------+--------------------------------------------------------------------------------------------------------------------------------+
| ``TraceloopCompatEmitter`` | Produces a Traceloop‑compatible span format for ecosystem bridging.                                                            |
+----------------------------+--------------------------------------------------------------------------------------------------------------------------------+

**Ordering**: Start phase – span emitters first (span context available early). Finish phase – span emitters last (other emitters observe live span).

Telemetry Flavors (``OTEL_INSTRUMENTATION_GENAI_EMITTERS``)
-----------------------------------------------------------
Baseline (choose one):

* ``span`` – spans only.
* ``span_metric`` – spans + metrics.
* ``span_metric_event`` – spans (lean) + metrics + content events (messages leave the span).

Extras (append):

* ``traceloop_compat`` – add Traceloop‑formatted span(s). If this is the **only** token provided, only the compat span is emitted.

Examples:

* ``span_metric_event,traceloop_compat`` – full semconv set + compatibility.
* ``traceloop_compat`` – compatibility only (no semconv spans/metrics/events).

Content Capture Matrix
----------------------
Environment variable ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` selects mode:

+------------------+-------------------------------+---------------------------------------------+
| Mode             | Span Flavors (span / metric)  | ``span_metric_event`` Flavor                |
+==================+===============================+=============================================+
| NO_CONTENT       | No messages on spans          | No events (no content)                      |
+------------------+-------------------------------+---------------------------------------------+
| SPAN_ONLY        | Messages on spans             | (treated like NO_CONTENT – keep spans lean) |
+------------------+-------------------------------+---------------------------------------------+
| EVENT_ONLY       | No messages on spans          | Messages as events                          |
+------------------+-------------------------------+---------------------------------------------+
| SPAN_AND_EVENT   | Messages on spans             | Messages as events (span kept lean)         |
+------------------+-------------------------------+---------------------------------------------+

Evaluation (Asynchronous Model)
-------------------------------
**Goal**: Avoid blocking request latency while still emitting quality / compliance / guardrail metrics.

Flow:

1. ``stop_llm`` is called.
2. Each configured evaluator *samples* the invocation (rate limit + custom logic via ``should_sample``).
3. Sampled invocations are enqueued (very fast). Sampling decisions are recorded under ``invocation.attributes['gen_ai.evaluation.sampled']``.
4. A background thread (interval = ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL``) drains queues and calls ``evaluate_invocation`` per item.
5. Results → histogram metric (``gen_ai.evaluation.score``) + aggregated event (``gen_ai.evaluations``) + optional spans.

Synchronous (legacy / ad hoc): ``TelemetryHandler.evaluate_llm(invocation)`` executes evaluators immediately.

Manual Flush (e.g., short‑lived scripts / tests):

.. code-block:: python

   handler.process_evaluations()  # one drain cycle

Sampling & Rate Limiting
~~~~~~~~~~~~~~~~~~~~~~~~
* Per‑evaluator sliding window rate limiting: set ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE``.
* Zero / unset → unlimited.
* Implement ``Evaluator.should_sample(invocation)`` for custom (probability / attribute / content–based) policies.

Evaluator Interface (Current)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: python

   from opentelemetry.util.genai.evaluators.base import Evaluator
   from opentelemetry.util.genai.types import LLMInvocation, EvaluationResult

   class MyEvaluator(Evaluator):
       def should_sample(self, invocation: LLMInvocation) -> bool:
           return True  # or custom logic

       def evaluate_invocation(self, invocation: LLMInvocation):
           # heavy work here
           return EvaluationResult(metric_name="custom", score=0.87, label="ok")

Register via ``register_evaluator("custom", lambda: MyEvaluator())``.

Traceloop Compatibility
-----------------------
If you already rely on Traceloop semantics or tooling:

* Add ``traceloop_compat`` to ``OTEL_INSTRUMENTATION_GENAI_EMITTERS``.
* Or run *only* the compat emitter by setting the variable to ``traceloop_compat``.
* Compat spans can coexist with semconv spans – helpful for transition or side‑by‑side validation.

Upload Hooks
------------
Optional persistence of prompt/response artifacts (e.g. fsspec to local disk or object storage):

* Configure ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK`` with an import path to a factory returning an object with an ``upload(...)`` method.
* ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` provides the storage root (e.g. ``/tmp/prompts`` or ``s3://bucket/path``).

Quick Start
-----------
Minimal synchronous example (no async flush – good for services):

.. code-block:: python

   from opentelemetry.util.genai.handler import get_telemetry_handler
   from opentelemetry.util.genai.types import LLMInvocation, InputMessage, OutputMessage, Text

   handler = get_telemetry_handler()
   inv = LLMInvocation(request_model="demo-model", provider="demo")
   inv.input_messages.append(InputMessage(role="user", parts=[Text(content="Hello?")]))

   handler.start_llm(inv)
   # ... call model ...
   inv.output_messages.append(OutputMessage(role="assistant", parts=[Text(content="Hi!")], finish_reason="stop"))
   handler.stop_llm(inv)  # schedules async evaluation if enabled

   # Optional: force evaluation processing (e.g., short script)
   handler.process_evaluations()

Environment Variables
---------------------
Core / Flavor / Content:

* ``OTEL_INSTRUMENTATION_GENAI_EMITTERS`` – flavor + extras (``span`` | ``span_metric`` | ``span_metric_event`` + optional ``traceloop_compat``).
* ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` – ``NO_CONTENT`` | ``SPAN_ONLY`` | ``EVENT_ONLY`` | ``SPAN_AND_EVENT``.
* ``OTEL_SEMCONV_STABILITY_OPT_IN`` – must include ``gen_ai_latest_experimental`` to unlock semantic attributes & content modes.

Evaluation:

* ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE`` – ``true`` / ``false``.
* ``OTEL_INSTRUMENTATION_GENAI_EVALUATORS`` – comma list (e.g. ``length,sentiment,deepeval``).
* ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE`` – ``off`` | ``aggregated`` | ``per_metric``.
* ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL`` – background drain interval (seconds, default 5.0).
* ``OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE`` – per‑evaluator sample cap (0 = unlimited).

Upload / Artifacts:

* ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK`` – path to hook factory.
* ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` – storage base path/URI.

Advanced Use Cases
------------------
* **High‑volume inference service** – Set flavor to ``span_metric_event`` + message capture via events to keep spans small; enable sampling with a low rate limit for costlier external evaluators.
* **Local benchmarking / quality lab** – Use synchronous ``evaluate_llm`` in a harness script for deterministic comparisons, or call ``process_evaluations`` at controlled checkpoints.
* **Migration from Traceloop** – Run ``span_metric_event,traceloop_compat`` and compare spans side‑by‑side before removing the compat emitter.
* **Selective evaluation** – Override ``should_sample`` to only evaluate certain models, routes, or request sizes.

Extensibility Summary
---------------------
+----------------------+-----------------------------------------------+
| Extension Point      | How                                           |
+======================+===============================================+
| Emitter              | Implement start/finish/error; add to pipeline |
+----------------------+-----------------------------------------------+
| Evaluator            | Subclass ``Evaluator``; register factory      |
+----------------------+-----------------------------------------------+
| Evaluation emitters  | (Advanced) Wrap EvaluationManager or fork     |
+----------------------+-----------------------------------------------+
| Upload hook          | Provide entry point or import path            |
+----------------------+-----------------------------------------------+

Troubleshooting
---------------
* **Missing evaluation data** – Ensure async drain occurred (call ``process_evaluations`` in short scripts).
* **Score always None (deepeval)** – External integration not installed; you’re seeing the placeholder.
* **High span size** – Switch to ``span_metric_event`` so message bodies move to events.
* **Sampling too aggressive** – Increase rate limit or adjust custom ``should_sample`` logic.

Migration Notes (from earlier synchronous-only evaluation versions)
-------------------------------------------------------------------
* ``evaluate_llm(invocation)`` still works and returns immediate results.
* Automatic evaluation now *queues*; rely on metrics/events after the worker drains.
* Add explicit ``handler.process_evaluations()`` in unit tests that assert on evaluation telemetry.

Stability Disclaimer
--------------------
GenAI semantic conventions and evaluation attributes are **incubating** and may evolve.
Monitor the CHANGELOG before pinning dashboards or alerts to specific attribute names.

License
-------
Apache 2.0 (see ``LICENSE``). Third‑party components retain their respective licenses.
