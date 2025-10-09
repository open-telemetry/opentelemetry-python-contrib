# OpenTelemetry GenAI Utility – Architecture (Implementation Aligned)

Status: Updated to reflect the current implementation in the *-dev package as of 2025‑10‑08.

This document supersedes earlier purely *target* design notes; it now describes the **actual implementation** and marks deferred items. For an audit of deltas between the original vision and code, see `README.implementation-findings.md`.

## 1. Goals (Why this utility exists)
Provide a stable, extensible core abstraction (GenAI Types + TelemetryHandler + CompositeEmitter + Evaluator hooks) separating *instrumentation capture* from *telemetry flavor emission* so that:
- Instrumentation authors create neutral GenAI data objects once.
- Different telemetry flavors (semantic conventions, vendor enrichments, events vs attributes, aggregated evaluation results, cost / agent metrics) are produced by pluggable emitters without touching instrumentation code.
- Evaluations (LLM-as-a-judge, quality metrics) run asynchronously and re-emit results through the same handler/emitter pipeline.
- Third parties can add / replace / augment emitters in well-defined category chains.
- Configuration is primarily environment-variable driven; complexity is opt-in.

Non-goal: Replace the OpenTelemetry SDK pipeline. Emitters sit *above* the SDK using public Span / Metrics / Logs / Events APIs.

## 2. Core Concepts
### 2.1 GenAI Types (Data Model)
Implemented dataclasses (in `types.py`):
- `LLMInvocation`
- `EmbeddingInvocation`
- `Workflow`
- `AgentInvocation`
- `Task`
- `ToolCall`
- `EvaluationResult` (atomic)

Planned (not yet implemented): `RetrievalInvocation`, `PlannerInvocation`, aggregated `EvaluationResults` wrapper (currently lists of `EvaluationResult` are passed directly).

Base dataclass: `GenAI` – fields include timing (`start_time`, `end_time`), identity (`run_id`, `parent_run_id`), context (`provider`, `framework`, `agent_*`, `system`, `conversation_id`, `data_source_id`), plus `attributes: dict[str, Any]` for free-form metadata.

Semantic attributes: fields tagged with `metadata={"semconv": <attr name>}` feed `semantic_convention_attributes()` which returns only populated values; emitters rely on this reflective approach (no hard‑coded attribute lists).

Messages: `InputMessage` / `OutputMessage` each hold `role` and `parts` (which may be `Text`, `ToolCall`, `ToolCallResponse`, or arbitrary parts). Output messages include `finish_reason`.

`EvaluationResult` fields: `metric_name`, optional `score` (float), `label` (categorical outcome), `explanation`, `error` (contains `type`, `message`), `attributes` (additional evaluator-specific key/values). No aggregate wrapper class yet.

### 2.2 TelemetryHandler
`TelemetryHandler` (formerly referred to as `Handler`) orchestrates lifecycle & evaluation emission.

Capabilities:
- Type-specific lifecycle: `start_llm`, `stop_llm`, `fail_llm`, plus `start/stop/fail` for embedding, tool call, workflow, agent, task.
- Generic dispatchers: `start(obj)`, `finish(obj)`, `fail(obj, error)`.
- Dynamic content capture refresh (`_refresh_capture_content`) each LLM / agentic start (re-reads env + experimental gating).
- Delegation to `CompositeEmitter` (`on_start`, `on_end`, `on_error`, `on_evaluation_results`).
- Completion callback registry (`CompletionCallback`); Evaluation Manager auto-registers if evaluators present.
- Evaluation emission via `evaluation_results(invocation, list[EvaluationResult])`.

### 2.3 Span / Trace Correlation
Invocation objects hold a `span` reference (if spans enabled). There is no separate captured-span-context snapshot object; emitters access the span directly. If spans are disabled, evaluation sampling falls back to queueing (trace-id sampling devolves to unconditional enqueue with a debug log).

## 3. Emitter Architecture
### 3.1 Protocol & Meta
`EmitterProtocol` offers: `on_start(obj)`, `on_end(obj)`, `on_error(error, obj)`, `on_evaluation_results(results, obj=None)`. Capability flags described in early design are **not implemented** (deferred). Invocation-type filtering is injected by wrapping `handles` when an `EmitterSpec` sets `invocation_types`.

`EmitterMeta` supplies `role`, `name`, optional `override`, and a default `handles(obj)` returning `True`. Role names are informational and may not match category names (e.g., `MetricsEmitter.role == "metric"`).

### 3.2 CompositeEmitter
Defines ordered category dispatch with explicit sequences:
- Start order: `span`, `metrics`, `content_events`
- End/error order: `evaluation`, `metrics`, `content_events`, `span` (span ends last so other emitters can enrich attributes first; evaluation emitters appear first in end sequence to allow flush behavior).

Public API (current): `iter_emitters(categories)`, `emitters_for(category)`, `add_emitter(category, emitter)`. A richer `register_emitter(..., position, mode)` API is **not yet implemented**.

### 3.3 EmitterSpec & Discovery
Entry point group: `opentelemetry_util_genai_emitters` (vendor packages contribute specs).

`EmitterSpec` fields:
- `name`
- `category` (`span`, `metrics`, `content_events`, `evaluation`)
- `factory(context)`
- `mode` (`append`, `prepend`, `replace-category`, `replace-same-name`)
- `after`, `before` (ordering hints – **currently unused / inert**)
- `invocation_types` (allow-list; implemented via dynamic `handles` wrapping)

Ordering hints will either gain a resolver or be removed (open item).

### 3.4 Configuration (Emitters)
Baseline selection: `OTEL_INSTRUMENTATION_GENAI_EMITTERS` (comma-separated tokens):
- `span` (default)
- `span_metric`
- `span_metric_event`
- Additional tokens -> extra emitters (e.g. `traceloop_compat`). If the only token is `traceloop_compat`, semconv span is suppressed (`only_traceloop_compat`).

Category overrides (`OTEL_INSTRUMENTATION_GENAI_EMITTERS_<CATEGORY>` with `<CATEGORY>` = `SPAN|METRICS|CONTENT_EVENTS|EVALUATION`) support directives: `append:`, `prepend:`, `replace:` (alias for `replace-category`), `replace-category:`, `replace-same-name:`.

### 3.5 Invocation-Type Filtering
Implemented through `EmitterSpec.invocation_types`; configuration layer replaces/augments each emitter’s `handles` method to short‑circuit dispatch cheaply. No explicit positional insertion API yet; runtime additions can call `add_emitter` (append only).

### 3.6 Replace vs Append Semantics
Supported modes: `append`, `prepend`, `replace-category` (alias `replace`), `replace-same-name`. Ordering hints (`after` / `before`) are present but inactive.

### 3.7 Error Handling
CompositeEmitter wraps all emitter calls; failures are debug‑logged. Error metrics hook (`genai.emitter.errors`) is **not yet implemented** (planned enhancement).

## 4. Built-In Telemetry Emitters
### 4.1 SpanEmitter
Emits semantic attributes, optional input/output message content, system instructions, function definitions, token usage, and agent context. Finalization order ensures attributes set before span closure.

### 4.2 MetricsEmitter
Records durations and token usage to histograms: `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, plus agentic histograms (`gen_ai.workflow.duration`, `gen_ai.agent.duration`, `gen_ai.task.duration`). Role string is `metric` (singular) – may diverge from category name `metrics`.

### 4.3 ContentEventsEmitter
Emits **one** structured log record summarizing an entire LLM invocation (inputs, outputs, system instructions) — a deliberate deviation from earlier message-per-event concept to reduce event volume. Agent/workflow/task event emission is commented out (future option).

### 4.4 Evaluation Emitters
Always present:
- `EvaluationMetricsEmitter` – fixed histograms:
  - `gen_ai.evaluation.relevance`
  - `gen_ai.evaluation.hallucination`
  - `gen_ai.evaluation.sentiment`
  - `gen_ai.evaluation.toxicity`
  - `gen_ai.evaluation.bias`
  (Legacy dynamic `gen_ai.evaluation.score.<metric>` instruments removed.)
- `EvaluationEventsEmitter` – event per `EvaluationResult`; optional legacy variant via `OTEL_GENAI_EVALUATION_EVENT_LEGACY`.

Aggregation flag affects batching only (emitters remain active either way).

Emitted attributes (core):
- `gen_ai.evaluation.name` – metric name
- `gen_ai.evaluation.score.value` – numeric score (events only; histogram carries values)
- `gen_ai.evaluation.score.label` – categorical label (pass/fail/neutral/etc.)
- `gen_ai.evaluation.score.units` – units of the numeric score (currently `score`)
- `gen_ai.evaluation.passed` – boolean derived when label clearly indicates pass/fail (e.g. `pass`, `success`, `fail`); numeric-only heuristic currently disabled to prevent ambiguous semantics
- Agent/workflow identity: `gen_ai.agent.name`, `gen_ai.agent.id`, `gen_ai.workflow.id` when available.

## 5. Third-Party Emitters (External Packages)
- Traceloop span compatibility (`opentelemetry-util-genai-emitters-traceloop`).
- Splunk evaluation aggregation / extra metrics (`opentelemetry-util-genai-emitters-splunk`).

## 6. Configuration & Environment Variables
| Variable | Purpose | Notes |
|----------|---------|-------|
| `OTEL_INSTRUMENTATION_GENAI_EMITTERS` | Baseline + extras selection | Values: `span`, `span_metric`, `span_metric_event`, plus extras
| `OTEL_INSTRUMENTATION_GENAI_EMITTERS_<CATEGORY>` | Category overrides | Directives: append / prepend / replace / replace-category / replace-same-name |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES` | `span|events|both|none` | **Requires** `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT(_MODE)` | Legacy capture controls | Deprecated path still honored |
| `OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS` | Evaluator config grammar | `Evaluator(Type(metric(opt=val)))` syntax supported |
| `OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION` | Aggregate vs per-evaluator emission | Boolean |
| `OTEL_INSTRUMENTATION_GENAI_EVALS_INTERVAL` | Eval worker poll interval | Default 5.0 seconds |
| `OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE` | Trace-id ratio sampling | Float (0–1], default 1.0 |
| `OTEL_GENAI_EVALUATION_EVENT_LEGACY` | Emit legacy evaluation event shape | Adds second event per result |

## 7. Extensibility Mechanics
### 7.1 Entry Point Flow
1. Parse baseline & extras.
2. Register built-ins (span/metrics/content/evaluation).
3. Load entry point emitter specs & register.
4. Apply category overrides.
5. Instantiate `CompositeEmitter` with resolved category lists.

### 7.2 Programmatic API (Current State)
`CompositeEmitter.add_emitter(category, emitter)` (append). A richer `register_emitter` API (mode + position) is **planned**.

### 7.3 Invocation Type Filtering
`EmitterSpec.invocation_types` drives dynamic `handles` wrapper (fast pre-dispatch predicate). Evaluation emitters see results independently of invocation type filtering.

## 8. Evaluators Integration
Entry point group: `opentelemetry_util_genai_evaluators`.

Evaluation Manager:
- Auto-registers if evaluators available.
- Trace-id ratio sampling via `OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE` (falls back if no span context).
- Parses evaluator grammar into per-type plans (metric + options).
- Aggregation flag merges buckets into a single list when true.
- Emits lists of `EvaluationResult` (no wrapper class yet).
- Marks invocation `attributes["gen_ai.evaluation.executed"] = True` post emission.

## 9. Lifecycle Overview
```
start_* -> CompositeEmitter.on_start(span, metrics, content_events)
finish_* -> CompositeEmitter.on_end(evaluation, metrics, content_events, span)
  -> completion callbacks (Evaluation Manager enqueues)
Evaluation worker -> evaluate -> handler.evaluation_results(list) -> CompositeEmitter.on_evaluation_results(evaluation)
```

## 10. Replacement & Augmentation Scenarios
| Scenario | Configuration | Outcome |
|----------|---------------|---------|
| Add Traceloop compat span | `OTEL_INSTRUMENTATION_GENAI_EMITTERS=span,traceloop_compat` | Semconv + compat span |
| Only Traceloop compat span | `OTEL_INSTRUMENTATION_GENAI_EMITTERS=traceloop_compat` | Compat span only |
| Replace evaluation emitters | `OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=replace:SplunkEvaluationAggregator` | Only Splunk evaluation emission |
| Prepend custom metrics | `OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS=prepend:MyMetrics` | Custom metrics run first |
| Replace content events | `OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=replace:VendorContent` | Vendor events only |
| Agent-only cost metrics | (future) programmatic add with invocation_types filter | Metrics limited to agent invocations |

## 11. Error & Performance Considerations
- Emitters sandboxed (exceptions suppressed & debug logged).
- No error metric yet (planned: `genai.emitter.errors`).
- Content capture gated by experimental opt-in to prevent accidental large data egress.
- Single content event per invocation reduces volume.
- Invocation-type filtering occurs before heavy serialization.

## 12. Shared Utilities
`emitters/utils.py` includes: semantic attribute filtering, message serialization, enumeration builders (prompt/completion), function definition mapping, finish-time token usage application. Truncation / hashing helpers & PII redaction are **not yet implemented** (privacy work deferred).

## 13. Future Considerations
- Implement ordering resolver for `after` / `before` hints.
- Programmatic rich registration API (mode + position) & removal.
- Error metrics instrumentation.
- Aggregated `EvaluationResults` wrapper (with evaluator latency, counts).
- Privacy redaction & size-limiting/truncation helpers.
- Async emitters & dynamic hot-reload (deferred).
- Backpressure strategies for high-volume content events.

## 14. Non-Goals
Unchanged: Not replacing SDK exporters; no vendor-specific network export logic; minimal evaluation orchestration (queue + sampling + worker only).

## 15. Example End-to-End
```
pip install opentelemetry-util-genai \
            opentelemetry-util-genai-emitters-traceloop \
            opentelemetry-util-genai-emitters-splunk

export OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
export OTEL_INSTRUMENTATION_GENAI_EMITTERS=span_metric_event,traceloop_compat
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES=events
export OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE=0.5
export OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS="Deepeval(LLMInvocation(bias,toxicity))"

from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import LLMInvocation, InputMessage, OutputMessage, Text

handler = get_telemetry_handler()
inv = LLMInvocation(request_model="gpt-4", input_messages=[InputMessage(role="user", parts=[Text("Hello")])], provider="openai")
handler.start_llm(inv)
inv.output_messages = [OutputMessage(role="assistant", parts=[Text("Hi!")], finish_reason="stop")]
handler.stop_llm(inv)
handler.wait_for_evaluations(timeout=10)
```

## 16. Validation Strategy
- Unit tests: env parsing, category overrides, evaluator grammar, sampling, content capture gating.
- Future: ordering hints tests once implemented.
- Smoke: vendor emitters (Traceloop + Splunk) side-by-side replacement/append semantics.

## 17. Migration Notes
- `GeneratorProtocol` -> `EmitterProtocol` complete.
- Traceloop compat moved to external package.
- Evaluation emission is list of `EvaluationResult` (wrapper pending).
- Env parsing centralized in `config.parse_env` + build pipeline; handler only refreshes capture settings.

---
End of architecture document (implementation aligned).
