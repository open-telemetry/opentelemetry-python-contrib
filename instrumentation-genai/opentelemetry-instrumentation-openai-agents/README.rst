OpenTelemetry OpenAI Agents Instrumentation
==========================================

This package instruments OpenAI agent frameworks ("openai-agents") and forwards spans
into OpenTelemetry using the draft GenAI semantic conventions proposed upstream in
OpenTelemetry Semantic Conventions PR 2528_ (subject to change until stabilized).

Status: Experimental / Alpha

What You Get
------------
This instrumentation wires the OpenAI Agents (``openai-agents``) tracing hook into
OpenTelemetry and maps agent / tool / response span data to the draft GenAI
semantic conventions shipped alongside this package. It currently provides:

* Span kinds & names for ``create_agent``, ``invoke_agent``, ``execute_tool``, ``chat`` (responses), ``embeddings`` (when available)
* Core request attributes: model, max_tokens, temperature, top_p, top_k, penalties, stop sequences, seed, encoding formats
* Choice count (``gen_ai.request.choice.count``) when ``n``/``choice_count`` > 1
* Output type (``gen_ai.output.type``) from ``response_format.type``
* Response attributes: id, model, aggregated finish reasons
* Token usage (input/prompt + output/completion) from both span data or response object
* OpenAI specific: request / response service tier, system fingerprint
* Server endpoint host/port extraction (``server.address`` / ``server.port``)
* Conversation / thread id (``gen_ai.conversation.id``)
* Agent metadata: id, name, description
* Tool metadata: name, id, type, description; tool call arguments & results (opt‑in)
* Tool definitions (opt‑in) & orchestrator agent definitions
* Data source id for retrieval / RAG scenarios
* Optional input / output message capture with truncation
  - Messages are serialized to JSON strings (instead of raw lists of dicts) to comply with OpenTelemetry attribute type requirements and avoid exporter warnings.
* Events: user / assistant / tool messages, tool call + tool result, per-choice events
* Metrics (duration + token usage histograms) behind an env toggle
* Size guarding via JSON serialization + max length truncation (default 20 KB)

Usage
-----
.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    OpenAIAgentsInstrumentor().instrument()
    client = OpenAI()
    # run your agent framework (openai-agents) code

Configuration (Environment Variables)
-------------------------------------
Set these before importing / enabling instrumentation:

* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT`` (default ``false``)
  - When ``true`` records ``gen_ai.input.messages`` + ``gen_ai.output.messages`` and emits message events.
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_DEFINITIONS`` (default ``false``)
  - When ``true`` records ``gen_ai.tool.definitions`` (can be large & sensitive).
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO`` (default ``false``)
  - When ``true`` records tool call arguments / results & emits assistant/tool message events.
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS`` (default ``true``)
  - Set to ``false`` to disable ``gen_ai.operation.duration`` and ``gen_ai.token.usage`` histograms.
* ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_MAX_VALUE_LENGTH`` (default ``20480``)
  - Max serialized length for large attribute values (tool defs, messages, arguments, results). Values exceeding are truncated with ``...``.

Security & PII Note: Content, tool IO, and tool definitions may contain sensitive data. Leave toggles off in production unless required.

Metrics
-------
When metrics are enabled the following histograms are recorded:

* ``gen_ai.operation.duration`` (seconds) - per span operation duration.
* ``gen_ai.token.usage`` (tokens) - one data point per input/output token count with attribute ``gen_ai.token.type`` = ``input`` or ``output``.

Both include low‑cardinality attributes: ``gen_ai.provider.name``, ``gen_ai.operation.name``, and ``gen_ai.request.model`` (if available). Errors add ``error.type``.

Exporting to Azure Application Insights
---------------------------------------
Use the OpenTelemetry Azure Monitor exporter in your app:

.. code:: python

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(
        connection_string="InstrumentationKey=...;IngestionEndpoint=..."
    )

    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
    OpenAIAgentsInstrumentor().instrument()

    # start your agent workflow

The exporter will ship the agent / tool / model invocation spans with attributes
outlined in the upstream semantic conventions (see PR 2528_) (create_agent, invoke_agent,
execute_tool, etc.).

Truncation Strategy
-------------------
Large structured values are JSON serialized and truncated to the configured byte length (default 20480). This affects: tool definitions, tool arguments/results, input/output messages, orchestrator agent definitions. Truncation preserves valid UTF‑8 boundaries by operating on Python strings (code points) before final attribute assignment.

Limitations & Future Work
-------------------------
* No explicit instrumentation for streaming chunk events yet (would require upstream hooks) — intentionally deferred.
* Draft semantic conventions may evolve; attribute names could change before stabilization. When the schema version updates, re‑validate against the upstream semantic conventions (see PR 2528_).
* Extended test coverage is growing; please add cases when introducing new span data types or attributes (see existing tests for patterns).

Removed Previous Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The following earlier limitations have been addressed:

* Deactivation: ``uninstrument()`` now calls processor ``shutdown()`` which prevents new spans and ends any open ones.
* Operation naming: ``create_agent`` vs ``invoke_agent`` now prefers an explicit upstream flag (``is_creation``) and falls back to a refined heuristic (no parent + description implies creation).
* Additional span types (embeddings, transcription, speech, guardrail, handoff) are recognized with stable operation names.
* Metrics, truncation, tool IO/content gating all implemented and configurable.
* Time handling uses timezone-aware UTC timestamps; no deprecated ``datetime.utcnow`` usage.

Contributing
------------
Please add tests when extending attribute coverage or events. Keep attribute cardinality low for metrics. Avoid capturing content unless explicitly gated by an env var.

License
-------
Apache 2.0

.. _2528: https://github.com/open-telemetry/semantic-conventions/pull/2528
