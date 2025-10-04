OpenTelemetry GenAI Utilities (Concise Guide)
=============================================

Purpose
-------
Emit semantic telemetry (spans, metrics, content events, evaluation results) for GenAI workloads with a composable emitter pipeline and optional evaluator integration.

If you need the deep rationale and full architecture (categories, replacement semantics, third‑party emitters), see: ``README.architecture.md`` in the same directory.

Core Concepts
-------------
* Domain objects (``LLMInvocation``, ``EmbeddingInvocation``, etc.) capture request/response + timing.
* ``TelemetryHandler`` is the facade: start / stop / fail invocations, internally delegating to a ``CompositeEmitter``.
* Emitters are small components implementing ``EmitterProtocol`` with hooks: ``on_start``, ``on_end``, ``on_error``, ``on_evaluation_results`` (evaluation hook used only by evaluation category members).
* Categories: ``span``, ``metrics``; ``content_events``; ``evaluation`` (evaluation emitters fire only when evaluator results exist).

Quick Start
-----------
.. code-block:: python

   from opentelemetry.util.genai.handler import get_telemetry_handler
   from opentelemetry.util.genai.types import LLMInvocation, InputMessage, OutputMessage, Text

   handler = get_telemetry_handler()
   inv = LLMInvocation(request_model="demo-model", provider="demo")
   inv.input_messages.append(InputMessage(role="user", parts=[Text(content="Hello?")]))
   handler.start_llm(inv)
   # ... call model ...
   inv.output_messages.append(OutputMessage(role="assistant", parts=[Text(content="Hi!")], finish_reason="stop"))
   handler.stop_llm(inv)

Key Environment Variables
-------------------------
Content & Flavor:

* ``OTEL_INSTRUMENTATION_GENAI_EMITTERS`` = ``span`` | ``span_metric`` | ``span_metric_event`` (optionally add ``traceloop_compat`` after installing the Traceloop plug-in).
* ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` = ``NO_CONTENT`` | ``SPAN_ONLY`` | ``EVENT_ONLY`` | ``SPAN_AND_EVENT``.
* ``OTEL_SEMCONV_STABILITY_OPT_IN`` must include ``gen_ai_latest_experimental`` to enable GenAI attributes & content modes.

Evaluation:

* ``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS`` (list or ``none``).
* ``OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION`` = ``true`` to emit one aggregated event per invocation.

Artifacts / Upload:

* ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK`` – factory import path.
* ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` – storage root path / URI.

Emitter Composition (Current Status)
------------------------------------
Built via ``build_emitter_pipeline`` which:

1. Adds builtin semantic convention emitters based on flavor.
2. Optionally adds Traceloop compatibility span (still internal; extraction planned – see refactoring plan Tasks 13–14).
3. Always adds evaluation emitters (metrics + events + optional spans) when enabled.
4. Applies entry point specs & category overrides (append, prepend, replace-category, replace-same-name).

Extending with Entry Points
---------------------------
Register an entry point group ``opentelemetry_util_genai_emitters`` that returns one or more ``EmitterSpec`` objects (or dicts). Fields:
``name``, ``category``, ``factory``, optional ``mode`` (append|prepend|replace-category|replace-same-name), optional ``invocation_types`` (future filtering hook; planned Task 19).

Typical Scenarios
-----------------

* High throughput service: ``span_metric_event`` + ``EVENT_ONLY`` (spans stay small; messages move to events).
* Migration / ecosystem bridging: add ``traceloop_compat`` while keeping semantic spans for comparison.

Troubleshooting
---------------

* No GenAI attributes? Ensure stability opt-in includes ``gen_ai_latest_experimental``.
* Missing evaluation data? Check evaluator env variable or that evaluators are registered.
* Large spans? Switch to ``span_metric_event`` + ``EVENT_ONLY``.
* Need vendor metrics augmentation? Ship an emitter via entry point with metrics category and ``mode=append``.

Planned (Not Yet Implemented)
-----------------------------

* Traceloop extraction to its own distribution.
* Invocation type filtering (skips emitters for unrelated invocation objects).
* Metrics counters for emitter failures.

Stability
---------
GenAI semantic conventions are incubating; field names or categories may evolve. Track the refactoring progress in ``README.refactoring.emitters.md``.

Monitor the CHANGELOG before pinning dashboards or alerts to specific attribute names.

License
-------
Apache 2.0 (see ``LICENSE``). Third‑party components retain their respective licenses.
