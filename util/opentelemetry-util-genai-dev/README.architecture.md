# OpenTelemetry GenAI Utility Reference Architecture

> Document purpose: Prescriptive reference architecture for the refactor of the development PoC ( *-dev* packages ) into `opentelemetry-util-genai` and related emitter / evaluator extension packages. Describes the *target* design (not current PoC state). Backward compatibility is **not** a constraint for this refactor branch.

## 1. Goals (Why this utility exists)
Provide a stable, extensible core abstraction (GenAI Types + Handler + Emitters + Evaluator hooks) separating *instrumentation capture* from *telemetry flavor emission* so that:
- Instrumentation authors emit neutral GenAI data types once.
- Different telemetry “flavors” (OpenTelemetry semantic convention variants, vendor-specific enrichments, custom schemas, events vs span attributes, aggregated evaluation result events, cost metrics, etc.) are produced by pluggable emitters without changing instrumentation.
- Evaluations (LLM-as-a-judge, quality metrics) run asynchronously and re-emit results through the same unified Handler/Emitter pipeline.
- Third parties can add / replace / augment emitters in well-defined lifecycle insertion points with minimal coupling.
- Configuration happens via consistent environment variables; defaults are sensible; complexity is opt-in.

Non-goal: Reinvent the OpenTelemetry SDK export pipeline; emitters sit *above* the SDK using existing Span / Metric / Log / Event APIs.

## 2. Core Concepts
### 2.1 GenAI Types (Data Model)
Neutral, in-memory domain objects capturing invocation lifecycle independent of final telemetry encoding. Envisioned (extensible) set:
- `LLMInvocation`
- `AgentInvocation`
- `RetrievalInvocation`
- `EmbeddingInvocation`
- `WorkflowInvocation`
- `StepInvocation`
- `PlannerInvocation`
- `EvaluationResults` (represents a batch/list of individual `EvaluationResult` objects aggregated by evaluator logic or raw single result when not aggregated)

Common base shape (conceptual):
```
GenAIInvocation:
  id: str (stable unique id – UUID or deterministic)
  parent_id: Optional[str]
  span_context: CapturedSpanContext (snapshot at creation)
  start_time_ns: int
  end_time_ns: Optional[int]
  model/provider/tool identifiers (type-specific fields)
  input_messages: List[Message]
  output_messages: List[Message]
  system_messages: List[Message]
  tokens_prompt / tokens_completion / cost metrics (optional collected or provided later)
  attributes: MutableMapping[str, Any] (extensible metadata)
```
Messages hold role, content (structured parts), and optional metadata.

#### 2.1.1 LLMInvocation semantic attribute contract

`LLMInvocation` now exposes the semantic-convention friendly fields directly on the dataclass instead of hiding everything in the generic `attributes` dictionary. Each field carries metadata (`metadata={"semconv": <attribute name>}`) so emitters can enumerate the canonical keys without hard-coding property names. Highlights:

- Base `GenAI` class adds `system`, `conversation_id`, `data_source_id`, `agent_name`, and `agent_id` to mirror proposed semantics.
- Request knobs (`request_temperature`, `request_top_p`, `request_top_k`, `request_frequency_penalty`, `request_presence_penalty`, `request_stop_sequences`, `request_max_tokens`, `request_choice_count`, `request_seed`, `request_encoding_formats`) and response details (`response_model_name`, `response_id`, `response_finish_reasons`, `response_service_tier`, `response_system_fingerprint`) are first-class fields.
- Token usage (`input_tokens`, `output_tokens`) and output modality (`output_type`) likewise map 1:1 to semantic attributes.
- The helper `semantic_convention_attributes()` walks the dataclass field metadata to produce a dict of populated semantic attributes; built-in emitters use this instead of bespoke mapping tables.

The `attributes: Dict[str, Any]` bag is still present for vendor or instrumentation-specific metadata. Built-in emitters only read keys that already have a semantic prefix (`gen_ai.*`, `traceloop.*`, etc.); everything else stays in-process unless a plug-in cares about it. This keeps semantic output deterministic while allowing instrumentation to stash raw extras that other emitters (Traceloop, Splunk, custom) can enrich.

`EvaluationResult` (atomic) includes: metric_name, value (numeric or categorical), pass_fail (optional bool), confidence(optional), reasoning(optional), latency(optional), additional_attrs.

### 2.2 Handler
`Handler` is the façade used by instrumentation and evaluators. Responsibilities:
- Construct GenAI Types (factory helpers) capturing span context immediately (even if spans later suppressed or not emitted).
- Provide lifecycle methods: `start_*(invocation)` and `end_*(invocation)` OR a high-level context manager convenience.
- Delegate to a `CompositeEmitter` for actual telemetry emission at well-defined lifecycle points.
- Offer `evaluation_results(results: EvaluationResults)` for evaluators.
- Maintain optional registry of completion callbacks (e.g., Evaluation Manager) implementing `CompletionCallback.on_completion(gen_ai_invocation)`.

### 2.3 Span Context Capture
When a GenAI Type is instantiated, the active span (if any) is queried and encoded into a lightweight `CapturedSpanContext` containing trace_id, span_id, trace_flags, trace_state. This allows metrics/events emitters to correlate even if span emission is disabled.

## 3. Emitter Architecture
### 3.1 Emitter Protocol
`EmitterProtocol` replaces the earlier GeneratorProtocol idea. It defines the interface any emitter implements. Methods reference concrete GenAI Types (strong-typed union where practical) instead of loosely typed dicts.

Minimal protocol surface (sync for simplicity; an async variant could be added later if required):
```
class EmitterProtocol(Protocol):
  # Called when an invocation is started (before user logic runs)
  def on_start(self, invocation: GenAIInvocation) -> None: ...

  # Called when invocation finishes (success or failure). Invocation object now has end_time, outputs, errors populated.
  def on_end(self, invocation: GenAIInvocation) -> None: ...

  # Optional: handle aggregated evaluation batches
  def on_evaluation_results(self, results: EvaluationResults) -> None: ...

  # Capability flags (may be simple attributes):
  emits_spans: bool
  emits_metrics: bool
  emits_events: bool
```
Specialized subclasses MAY also exist (e.g., `SpanEmitter`, `MetricsEmitter`, `ContentEventsEmitter`, `EvaluationEmitter`) but they all adhere to the protocol so CompositeEmitter can treat them uniformly.

### 3.2 CompositeEmitter
Central orchestrator owning ordered emitter chains per lifecycle category. Categories (initial pragmatic set):
- `span_emitters` – produce/annotate spans
- `metrics_emitters` – produce metrics derived from invocations / evaluations
- `content_event_emitters` – emit structured log/event records for input/output/system messages
- `evaluation_emitters` – emit evaluation results representation (standard semantic conv or vendor aggregated flavor)

Responsibilities:
- Maintain insertion-ordered lists per category.
- Provide registration API supporting: append, prepend, replace (single category), conditional replace-by-type.
- Support third-party declarative registration via entry points and env-var overrides.
- Fan out lifecycle calls: on_start -> targeted categories (span emitters, maybe metrics preallocation), on_end -> span, metrics, content events; on_evaluation_results -> evaluation emitters (and optionally metrics emitters for evaluation metrics).
- Evaluate configuration precedence: (a) explicit programmatic registration, (b) env var directives (replace/append), (c) entry point defaults, (d) built-in defaults.

### 3.3 Registration & Discovery
Entry point group: `opentelemetry_util_genai_emitters`.

Each emitter package defines a single entry point referencing a function, typically named `load_emitters`, returning `List[EmitterSpec]`.

`EmitterSpec` (plain dict) minimal fields:
```
{
  "name": "SemanticConvSpan",            # unique logical name
  "kind": "span" | "metrics" | "content_events" | "evaluation",
  "factory": callable,                   # returns an EmitterProtocol instance
  "mode": "append" | "replace-category" | "replace-same-name",  # default append
  "position": "first" | "last" | "before:Name" | "after:Name",  # optional ordering hint
  "invocation_types": ["LLMInvocation", "AgentInvocation"],       # optional filter
}
```
This mirrors the simplicity of evaluator registration (one entry point -> many specs) and avoids rigid class contracts. Future fields can be added without breaking existing packages.

Resolution steps:
1. Collect all `EmitterSpec`s from builtins + entry points.
2. Apply ordering hints (single pass; unresolved references ignored with warning).
3. Apply `mode` semantics (`replace-category`, `replace-same-name`).
4. Apply environment variable overrides last.
5. Freeze chains (immutable lists) for cheap hot-path iteration.

Initial scope treats start/end the same; future phase hooks can extend `EmitterSpec` with e.g. `phases` if required.

### 3.4 Environment Variable Configuration (Emitters)
Target variables (illustrative naming; adjust for consistency with existing evaluator env var style):
```
OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN=
  comma-separated list of emitter names with optional position / mode hints
OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS=
OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=
OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=
```
Advanced syntax example (mirrors evaluator metric selection philosophy):
```
# Replace span emitter chain with SemanticConv + Traceloop extras appended
OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN="replace:SemanticConvSpan,TraceloopSpan"

# Append Splunk evaluation event aggregator, replacing standard evaluation content event emitter
OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION="replace-category:SplunkEvaluationAggregator"
```
(We keep parsing rules simple: prefix directives like `replace:` or `replace-category:`.)

CompositeEmitter performs parsing; Handler stays ignorant of env var parsing logic (single responsibility).

### 3.5 Lifecycle Insertion Points (Fine-Grained)
Beyond category-level ordering, third parties may request insertion for specific invocation types and phases. Provide API:
```
register_emitter(emitter, category, *, position="last", invocation_types=None, mode="append")
```
During emission, CompositeEmitter filters by invocation type if provided.

### 3.6 Replace vs Append Semantics
- `append` – emitter added after existing ones (default)
- `prepend` – added to front
- `replace-category` – wipes existing category chain, installs listed emitters
- `replace-same-name` – if emitter with same logical name exists, replace in-place; else append
- (future) `replace-first-of-category` – replace only first builtin keeping vendor augmentations (defer until concrete need).

### 3.7 Error Handling Strategy
Emitters should never raise upstream; CompositeEmitter wraps calls and logs errors (instrumentation must not break app flow). Provide minimal hook to collect error metrics.

## 4. Telemetry Flavor Examples
### 4.1 Semantic Convention Span Emitter (Built-In)
- Maps GenAI Invocation fields to proposed / existing OpenTelemetry semantic attributes (e.g., model name, token counts, message roles + truncated content, latency).
- Optionally sends message contents as attributes OR defers to content events emitter (config toggle `OTEL_GENAI_SPAN_ATTACH_MESSAGES=true|false`).

### 4.2 Content Events Emitter (Built-In)
- Emits structured log records (or span events if chosen) for each input / output / system message with ordering index and role.
- Could be replaced by Splunk aggregated event emitter for evaluation results only, while still keeping standard message events.

### 4.3 Metrics Emitter (Built-In)
- Emits counters (invocation_count), histograms (latency, prompt_tokens, completion_tokens, total_tokens), up-down counters (inflight_invocations), gauge-like observations (cost if available).
- Derives trace correlation via captured span context.

### 4.4 Evaluation Results Emitter (Built-In)
- If not aggregated: emits one log/event per `EvaluationResult` with metric name & value.
- If aggregated upstream (Manager sets `EvaluationResults` container), emits single aggregated log record referencing list.

## 5. Third-Party Emitter Examples
### 5.1 TraceloopEmitter (External Package `opentelemetry-util-genai-emitters-traceloop`)
Purpose: Extend semantic conventions with proprietary attributes absent (or contentious) in current spec (e.g. `traceloop.span.kind`, `request_top_p`, `request_temperature`, `agent_chain_depth`).

Design:
- Provides a `SpanEmitter` variant that wraps / decorates base Semantic Convention span emitter: either
  1. Replace-same-name mode OR
  2. Append after base span emitter and only add extra attributes (preferred to preserve baseline).
- Reuses shared mapping helpers from `opentelemetry.util.genai.emitters.util`.
- Registers via entry point EmitterSpec with `kind="span"`, `mode="append"`, `invocation_types=None`.

Example `EmitterSpec` inside `load_emitters()`:
```
def load_emitters():
    return [
        {
          "name": "TraceloopSpan",
          "kind": "span",
          "factory": lambda: TraceloopSpanEmitter(base_helpers=semantic_helpers),
          "position": "after:SemanticConvSpan",
          "mode": "append"
        }
    ]
```

Usage scenario: User installs package; by default Traceloop attributes now appear. User can disable by overriding env var to exclude name.

### 5.2 SplunkEmitter (External Package `opentelemetry-util-genai-emitters-splunk`)
Purpose: Provide vendor-specific enriched evaluation aggregation & optional metrics enrichment.

Components:
- `SplunkEvaluationAggregator` (category `evaluation`, mode `replace-category` if user chooses) – emits one event containing list of evaluation results plus summarized message previews.
- `SplunkExtraMetricsEmitter` (category `metrics`, mode `append`) – emits cost, model usage, or agent step custom metrics not yet in semantic conventions.

Composite configuration examples:
```
# Replace only evaluation emitter chain with Splunk aggregator
export OTEL_GENAI_EMITTERS_EVALUATION="replace-category:SplunkEvaluationAggregator"

# Append Splunk metrics emitter while keeping default metrics
export OTEL_GENAI_EMITTERS_METRICS="append:SplunkExtraMetrics"
```
If both Splunk and base evaluation emitter active (user chooses append), Splunk could mark events with vendor attribute `vendor="splunk"` to allow consumer filtering.

## 6. Configuration & Environment Variables (Proposed Set)
Evaluator env vars already exist pattern-wise; emitters follow similar naming.

Core toggles:
```
OTEL_INSTRUMENTATION_GENAI_ENABLE=true|false (master switch)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES=span|events|both|none (controls mapping strategy; defaults to events)

# Emitter chain directives
OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=...

# Evaluation manager aggregation toggle (consumed by evaluators, influences evaluation_results emission path)
OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION=true|false
```
Parsing keeps grammar intentionally narrow: comma-separated tokens; optional directive prefix preceding first token.

## 7. Extensibility Mechanics
### 7.1 Entry Point Discovery Flow
1. CompositeEmitter initialization.
2. Load builtin emitters (semantic conv baseline) into chains.
3. Discover third-party entry points -> collect specs.
4. Apply ordering + mode semantics.
5. Apply env var chain overrides (final authority).
6. Lock in final emitter lists (immutable for runtime simplicity) unless explicit dynamic modification API used.

### 7.2 Programmatic API Examples
```
from opentelemetry.util.genai import Handler, CompositeEmitter, SemanticConvEmitters

composite = CompositeEmitter.default()
# Programmatically add a custom metrics emitter for only AgentInvocation
composite.register_emitter(
  MyAgentMetricsEmitter(),
  category="metrics",
  position="last",
  invocation_types={"AgentInvocation"},
  mode="append"
)
handler = Handler(emitter=composite)
```

### 7.3 Invocation-Type Filtering
Emitters that declare `invocation_types` only receive lifecycle calls for those types. Evaluation emitters see `EvaluationResults` independently of invocation type filters.

## 8. Evaluators Integration
Evaluators (external packages) register via `opentelemetry_util_genai_evaluators` entry point group. The Evaluator Manager:
- Implements `CompletionCallback` and is registered with Handler.
- Samples finished invocations (Sampler protocol) and enqueues for asynchronous evaluation.
- Periodically drains queue, runs each evaluator’s `evaluate()` returning `List[EvaluationResult]`.
- Aggregates results to `EvaluationResults` if `OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION=true` else emits individually.
- Calls `handler.evaluation_results(...)` which triggers CompositeEmitter -> evaluation emitters.

Evaluators code strictly against GenAI Types (not specific telemetry), ensuring portability across flavors.

## 9. Lifecycle Overview
Sequence (simplified):
```
Instrumentation -> handler.start(invocation)
  -> composite.on_start(invocation)
User code executes / model call
Instrumentation -> handler.end(invocation)
  -> composite.on_end(invocation)
  -> completion callbacks (evaluator manager) invoked
Evaluator Manager (async) -> evaluate -> handler.evaluation_results(batch)
  -> composite.on_evaluation_results(batch)
SDK exporters forward produced spans/metrics/logs to backends
```

## 10. Replacement vs Augmentation Scenarios
| Scenario | User Intent | Configuration | Outcome |
|----------|-------------|---------------|---------|
| Add Traceloop extras | Keep baseline spans + add attrs | install pkg (auto append) | Two span emitters run sequentially; second adds attributes |
| Replace evaluation emission with Splunk aggregator | Want single aggregated event | `OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=replace-category:SplunkEvaluationAggregator` | Only Splunk emitter processes evaluation results |
| Add custom cost metrics only for LLMInvocation | Append targeted metrics | programmatic registration with invocation_types | Metrics chain emits cost metrics only on LLM invocations |
| Append metrics only for AgentInvocation while extending evaluation events | Enhance agent metrics, keep base evaluation events | programmatic registration with invocation_types={"AgentInvocation"} | Additional metrics produced only for agent invocations; evaluation events unaffected |
| Replace standard EvaluationResults emitter but keep message content events | Vendor aggregated evaluation events only | env var replace-category for evaluation chain | Evaluation results aggregated into single vendor event; message events still produced individually |
| Keep baseline spans but completely replace content events | Use proprietary message event schema | `OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=replace-category:VendorMsgEvents` | Only vendor message events emitted; spans & other categories unaffected |

## 11. Error & Performance Considerations
- Emitters must be lightweight; heavy processing (like large content redaction or summarization) should happen asynchronously or in evaluator layer.
- Guard rails: size limits for message content attributes, truncation helpers in shared utils.
- CompositeEmitter wraps each emitter call in try/except; errors increment internal counter metric `genai.emitter.errors` with labels (emitter_name, category, phase).
- Handler optionally exposes a debug flag to log emitter ordering & configuration resolution.
- Invocation-type filtering executed before expensive work (e.g., deep serialization) to minimize overhead.

## 12. Minimal Shared Utilities
`opentelemetry.util.genai.emitters.util` provides:
- Attribute mapping helpers (e.g., map_invocation_to_span_attrs(invocation))
- Token & cost normalization helpers
- Truncation & hashing functions for large inputs
- Safe serialization (to JSON) for events

## 13. Future Considerations (Not in initial scope)
- Async emitter interface for IO-bound enrichments.
- Dynamic runtime reconfiguration (hot swap emitters) – currently static after init.
- Fine-grained privacy redaction policies / PII classifiers (pluggable later).
- Backpressure / queue for high-volume content events (initial impl synchronous with small volume assumption).
- Unified schema version negotiation among emitters (version attribute for future migrations).

## 14. Non-Goals
- Replacing OpenTelemetry SDK exporters.
- Providing vendor-specific network export logic (handled at telemetry pipeline level already).
- Building a full evaluation orchestration framework beyond sampler + worker loop (focus remains narrow).

## 15. Example End-to-End Setup
```
# 1. User installs base + traceloop + splunk packages
pip install opentelemetry-util-genai opentelemetry-util-genai-emitters-traceloop opentelemetry-util-genai-emitters-splunk

# 2. Configure env vars
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES=events
export OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=replace-category:SplunkEvaluationAggregator

# 3. Instrumentation code
handler = get_global_genai_handler()  # returns singleton Handler
with handler.start_llm_invocation(model="gpt-4", input_messages=[...]) as inv:
    inv.add_output_message(...)
# Upon exit, emitters run; evaluator manager enqueues invitation

# 4. Evaluations produced asynchronously -> Splunk aggregated event
```

## 16. Validation Strategy for Refactor
- Unit tests: ordering resolution, env var parsing, replacement semantics, invocation-type filtering, evaluator integration.
- Property tests (optional): ensure no emitter raises propagates.
- Integration smoke: Traceloop + Splunk side-by-side.

## 17. Migration Notes from *-dev PoC
- Rename GeneratorProtocol -> EmitterProtocol.
- Move TraceloopCompatEmitter out of built-ins into dedicated `-emitters-traceloop` package; rename to `TraceloopSpanEmitter` (or simply `TraceloopEmitter` if only spans now, can later expand with metrics).
- Continue using the `OTEL_INSTRUMENTATION_GENAI_*` namespace uniformly for both emitters and evaluator-related configuration.
- Shift env var parsing from handler to CompositeEmitter.

---
This document should guide the implementation tasks in the refactor branch. Keep initial implementation lean; add complexity only when a concrete use case materializes.
