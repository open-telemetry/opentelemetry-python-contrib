# ADR 0001: Refactor to Composite Generators Architecture

Status: Proposed
Date: 2025-09-24
Authors: Architecture Review Initiative
Supersedes: N/A
Related: FEEDBACK.md

## 1. Context
The current implementation focuses on a single span generator for GenAI invocations. Planned expansion introduces: metrics, events, evaluation result emission, external vendor-specific generators (Traceloop), and override-style generators (Splunk evaluation aggregation). Original direction risked deep inheritance chains and per-type/per-channel class explosion.

We need to:
- Support 3 telemetry "flavors":
  1. span
  2. span_metric
  3. span_metric_event
- Allow external plugin packages:
  - `opentelemetry-util-genai-generators-traceloop` (span override + proprietary attributes) — STILL must emit semantic conventions span attributes for compatibility.
  - `opentelemetry-util-genai-generators-splunk` (custom evaluation results event schema; aggregate all evaluation results into a single event).
- Enforce rule: All metrics and events must be emitted in the logical context of the invocation span (span must be active during those emissions).
- Support data capture policy differences:
  - span, span_metric: captured message content (input/output) appended as span attributes.
  - span_metric_event: captured content emitted as events (input event, output event, tool call events, etc.) + metrics + a lean span with summary attributes only.
- Keep backward-compatible stable API surface while enabling addition of new emitters/evaluators.

## 2. Architectural Decision
Adopt a composition-first generator architecture based on role-oriented emitters orchestrated by a `CompositeGenerator` built dynamically per flavor + plugin overrides. Avoid deep inheritance and per-type/per-channel subclassing.

## 3. Core Concepts
### 3.1 Data Types (Domain Objects)
- `LLMInvocation`
- `EmbeddingInvocation`
- `ToolCall`
- `EvaluationResult`
- `Error`
- Additional future: `RetrievalInvocation`, `RerankInvocation` (extensible).

Data objects remain pure (no emission logic).

### 3.2 Emission Phases
Phases for an invocation life cycle:
- `start(invocation)`
- `finish(invocation)` — triggers evaluation before final span end
- `error(invocation, error)` — failure path (skip evaluation)

### 3.3 Roles (Emitter Responsibilities)
Roles define semantic responsibilities instead of inheritance:
- `span` (start/end span; ensure active context)
- `metric` (emit counters/gauges/histograms)
- `content_event` (emit input/output/tool call content as events)
- `evaluation_result` (emit evaluation results; may be per-result or aggregated)

Each emitter declares:
```python
class EmitterSpec(Protocol):
    role: str  # e.g. 'span', 'metric', 'content_event', 'evaluation_result'
    name: str
    handles_types: set[type]  # domain object classes it understands
    override: bool  # indicates it replaces default emitters for its role
```

### 3.4 CompositeGenerator
- Accepts ordered list of emitters.
- Guarantees ordering constraints:
  1. span emitters run first on start
  2. content_event (input) can run after span start (during start phase if configured)
  3. metric/event output emission occurs in finish AFTER output is populated but BEFORE span attributes finalization
  4. evaluation_result emission occurs before span end (span remains active to satisfy "in span context")
  5. span emitter `finish` runs last.

### 3.5 Evaluation Pipeline
Handler logic for finish:
1. `composite.finish(invocation)` (span still open; output metrics/events emitted)
2. If evaluation enabled: run evaluators -> list[EvaluationResult]
3. Pass results to composite: `composite.start(result)` / `finish(result)` (or aggregated emitter handles all in one pass)
4. Finally end span (span emitter last action).

### 3.6 Flavor to Role Mapping
| Flavor | Roles Activated | Data Capture Strategy |
|--------|-----------------|------------------------|
| span | span | Append content as span attributes (if capture enabled) |
| span_metric | span, metric | Append content as span attributes; metrics for tokens/latency/etc. |
| span_metric_event | span, metric, content_event | Content NOT stored on span (except minimal summaries); emitted as events; metrics emitted; evaluation results as events |

Evaluation result role is conditionally added based on evaluator presence.

### 3.7 Data Capture Modes
Environment: `OTEL_GENAI_CAPTURE_CONTENT=none|input|output|full`
- For span & span_metric flavors: attributes naming convention `gen_ai.prompt.messages.N.role`, `gen_ai.prompt.messages.N.content`, `gen_ai.completion.messages.N.*`.
- For span_metric_event flavor: events:
  - Event name examples:
    - `gen_ai.input_messages`
    - `gen_ai.output_messages`
    - `gen_ai.tool_call` (one per tool call if needed)
  - Span attributes store counts: `gen_ai.prompt.messages.count`, `gen_ai.completion.messages.count`.
  - Optionally hashes: `gen_ai.prompt.hash`, `gen_ai.completion.hash` (for correlation w/o content duplication).

### 3.8 Plugin Override Mechanics
Entry point groups:
- `opentelemetry_genai.generators`
- `opentelemetry_genai.evaluators`

Plugin factory returns list[EmitterSpec] or single spec.

Resolution algorithm:
1. Load core default emitter specs per role.
2. Discover plugin specs.
3. Apply explicit overrides from config variable `OTEL_GENAI_PLUGIN_OVERRIDES`:
   - Format: `role:name,role:name` (e.g. `span:traceloop,evaluation_result:splunk`)
4. Any plugin with `override=True` for a role (and selected) replaces *all* default emitters for that role.
5. If multiple override candidates chosen for same role -> choose first in override list; log warning.
6. Remaining roles use defaults.

### 3.9 External Packages
- `opentelemetry-util-genai-generators-traceloop`:
  - Provides `TraceloopSpanEmitter` (role=span, override optional; activated via override config or by flavor if `OTEL_GENAI_SPAN_VENDOR=traceloop`).
  - Ensures semantic convention attrs + vendor attrs under `traceloop.*` namespace.
  - Must not remove mandatory semconv attributes.

- `opentelemetry-util-genai-generators-splunk`:
  - Provides `SplunkEvaluationResultEmitter` (role=evaluation_result, override=True) aggregating all evaluation results into a single event:
    - Event name: `gen_ai.evaluations`
    - Attributes: aggregated metrics array / object (e.g. `gen_ai.evaluations.metrics=[{name,score,label},...]`).
    - Optionally attach summary stats (mean, min, max, count).

### 3.10 Error Handling
Failure path (`error(invocation, err)`):
Sequence for any flavor:
1. Ensure span started (if not, start + mark as errored).
2. Attach error attributes (semconv + vendor if plugin).
3. Optionally emit partial input content (only if capture mode includes input and policy allows on error).
4. Do NOT emit metrics/events that rely on completion tokens.
5. End span.
6. No evaluation execution.

### 3.11 Evaluation Emission per Flavor
| Flavor | Standard Path | With Splunk Override |
|--------|---------------|----------------------|
| span | span attrs per evaluation: `gen_ai.evaluation.<metric>.score` | One aggregated event; minimal summary attrs added to span (counts) |
| span_metric | span attrs + metrics per evaluation (e.g., gauge) | Aggregated event + metrics (if plugin chooses) |
| span_metric_event | one event per evaluation result (or per metric) | Single aggregated event replacing per-result events |

### 3.12 Span Context Guarantee
- Span emitter keeps span open until all emitters for finish + evaluation_result role complete.
- Composite enforces ordering; evaluation result emitter inserted before final span close callback.

## 4. Configuration Summary
Environment Variables (core):
- `OTEL_GENAI_FLAVOR=span|span_metric|span_metric_event`
- `OTEL_GENAI_CAPTURE_CONTENT=none|input|output|full`
- `OTEL_GENAI_PLUGIN_OVERRIDES=role:name[,role:name...]` (explicit plugin activation/override)
- `OTEL_GENAI_EXPERIMENTAL_ATTRS=0|1`
- `OTEL_GENAI_SPAN_VENDOR=semconv|traceloop` (syntactic sugar; maps to span override)

Derived internal config object:
```python
@dataclass(frozen=True)
class GenAIConfig:
    flavor: Flavor
    capture_content: CaptureMode
    plugin_overrides: dict[str,str]
    experimental_attrs: bool
    span_vendor: str | None
```

## 5. Build / Initialization Flow
1. Read env → GenAIConfig
2. Discover plugins → list[EmitterSpec]
3. Build role registry (defaults + apply overrides)
4. Assemble ordered emitters list per flavor
   - span flavor: [span, metric? (none), content_event? (none), evaluation_result?] (evaluation_result only if evaluators configured)
   - span_metric: [span, metric, evaluation_result?]
   - span_metric_event: [span, metric, content_event, evaluation_result?]
5. Create `CompositeGenerator(emitters)`
6. Instantiate `TelemetryHandler(generator=composite, evaluators=[...])`

## 6. Refactoring Steps
### Phase 1: Core Interfaces & Composite
- Introduce `interfaces.py`: `GeneratorProtocol`, `EvaluatorProtocol`.
- Migrate existing span logic to `emitters/span_semconv.py` as `SemconvSpanEmitter`.
- Implement `composite.py` with ordered role enforcement.
- Add `builder.py` to construct composite from config (initially only built-in span emitter).
- Update existing handler to use builder output.
- Add tests for lifecycle (start/finish/error) and ordering guarantees.

### Phase 2: Flavors & Data Capture Strategy
- Implement data capture policy module `capture.py`.
- Add metric emitter (token count, duration) → `emitters/metrics_semconv.py`.
- Add content event emitter → `emitters/content_events_semconv.py`.
- Implement flavor mapping logic.
- Add tests for each flavor verifying where content lands (span attrs vs events).

### Phase 3: Evaluation Pipeline
- Add evaluator protocol & stub evaluator.
- Implement default evaluation result emission strategies:
  - span flavor: attribute aggregator
  - span_metric: attributes + per-metric gauge (if available)
  - span_metric_event: per-result events
- Update handler finish logic to run evaluation before span close.
- Tests: evaluation results presence per flavor.

### Phase 4: Plugin Discovery & Override System
- Implement entry point loading in `plugins.py`.
- Add resolution algorithm & `OTEL_GENAI_PLUGIN_OVERRIDES` parsing.
- Provide developer docs with plugin template.
- Tests: mock entry points; ensure override precedence.

### Phase 5: Traceloop Span Plugin Support
- Define expected plugin spec contract doc.
- Add adapter injection point for vendor attributes.<br>
- Provide test harness simulating traceloop plugin returning override span emitter.

### Phase 6: Splunk Evaluation Aggregation Plugin Support
- Define aggregated event schema contract doc.
- Implement fallback aggregator if plugin present (core must NOT emit standard eval events when override active).
- Tests: ensure only single aggregated event emitted; no per-result duplication.

### Phase 7: Harden & Document
- Add metrics for internal instrumentation (optional): counts of invocations, failures, evaluation count.
- Provide upgrade guide referencing semconv version.
- Add ADR cross-links.

## 7. Ordering Rules (Detailed)
Start Phase Order:
1. span.start(invocation)
2. content_event.start(invocation) (input messages) [only in span_metric_event flavor & capture input]
3. metric.start(invocation) (prompt token count optional)

Finish Phase Order:
1. metric.finish(invocation) (compute durations, completion tokens)
2. content_event.finish(invocation) (output messages, tool calls)
3. evaluation_result.start/finish(EvaluationResult(s))
4. span.finish(invocation)

Error Phase Order:
1. span.error(invocation, err)
2. (optional) content_event.start(invocation) for input content if allowed
3. span.finish(invocation)  (end span)
(No metrics/events/evaluations)

## 8. Extensibility / Future
- Middleware chain can be inserted at composite level if cross-cutting concerns (PII scrubbing) arise.
- Additional roles (e.g., `log`) can be appended without breaking existing API.
- Evaluation results could later support streaming by adding `stream_evaluation(result)` hook (deferred).

## 9. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Plugin override conflicts | Deterministic order + warnings + first-wins policy |
| Span not active during metrics/events | Composite enforces ordering; tests assert current span context |
| Schema drift (splunk/traceloop) | Require plugins to pass semconv compliance checklist + test fixtures |
| Performance overhead (composition) | Emitters kept minimal; small list iterations |
| Backward compatibility of env vars | Support legacy vars with deprecation warning mapping |

## 10. Testing Strategy
- Unit tests per flavor verifying emission distribution.
- Plugin resolution tests with mock entry points (pkg_resources/importlib.metadata).
- Ordering tests using a probe emitter recording sequence.
- Context tests verifying active span during metric/event emission.
- Evaluation aggregation tests for Splunk plugin simulation.
- Error path tests verifying no metrics/events on failure.

## 11. Migration Notes
- Existing users: no code changes; default flavor = `span` (backward compatible).
- Setting `OTEL_GENAI_FLAVOR=span_metric_event` automatically moves content off span into events.
- Traceloop adopts plugin path; instruct users to set either `OTEL_GENAI_PLUGIN_OVERRIDES=span:traceloop` or `OTEL_GENAI_SPAN_VENDOR=traceloop`.

## 12. Open Questions
- Should evaluation metrics also become OTel metrics? (Planned but can be gated by feature flag later.)
- Standardized hashing algorithm for content summaries? (TBD: SHA256 vs murmur3) — choose SHA256 first.
- Maximum message size threshold for content attributes/events? (Add truncation policy in capture module.)

## 13. Acceptance Criteria
- Composite architecture in place with tests.
- All three flavors supported.
- Evaluation results emitted per flavor rules.
- Plugin override mechanism functioning with mock plugins.
- Documentation updated (README + FEEDBACK + plugin how-to).
- Backward compatibility maintained for legacy span-only consumers.

## 14. Appendices
### 14.1 Example Env Configurations
Span only with traceloop span override:
```
OTEL_GENAI_FLAVOR=span
OTEL_GENAI_SPAN_VENDOR=traceloop
OTEL_GENAI_CAPTURE_CONTENT=input
```
Full flavor with events & splunk eval aggregation:
```
OTEL_GENAI_FLAVOR=span_metric_event
OTEL_GENAI_CAPTURE_CONTENT=full
OTEL_GENAI_PLUGIN_OVERRIDES=evaluation_result:splunk
```

### 14.2 Minimal Plugin Skeleton
```python
# entry point: opentelemetry_genai.generators = traceloop=traceloop_plugin:emitters
from opentelemetry.util.genai.plugins import EmitterSpecBase

class TraceloopSpanEmitter(EmitterSpecBase):
    role = "span"
    name = "traceloop"
    handles_types = {LLMInvocation}
    override = True  # if replacing default; False if co-existing

    def start(self, obj): ...  # start span + semconv + vendor attrs
    def finish(self, obj): ...
    def error(self, obj, err): ...

def emitters():
    return [TraceloopSpanEmitter()]
```

## 15. Decision
Proceed with implementation as outlined; revisit aggregator vs per-result evaluation result emission after collecting real user feedback (post Phase 3) — Splunk plugin acts as first validation of override viability.

---
END ADR 0001

