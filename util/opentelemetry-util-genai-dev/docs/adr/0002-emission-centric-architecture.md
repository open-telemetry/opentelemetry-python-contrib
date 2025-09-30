# ADR 0002: Emission-Centric Architecture & Retirement of Legacy Generator Classes

Status: Proposed  
Date: 2025-09-27  
Authors: GenAI Telemetry Working Group  
Supersedes: Portions of initial multi-class generator proposal  
Related: `FEEDBACK.md`, `ADR 0001` (Composite Generators Refactor)

## 1. Context
Earlier iterations introduced a `generators/` package with multiple base and concrete *Generator* classes (span, metric, event, evaluation, etc.). Ongoing evolution showed:
- The class hierarchy added boilerplate without delivering the flexibility it was designed for.
- Real divergence of behavior is emerging mainly across "telemetry flavor" (span | span_metric | span_metric_event) and vendor/plugin extensions (Traceloop, Splunk evaluation aggregation).
- We need a leaner, composition-based emission layer that centralizes ordering, keeps spans open while emitting derived telemetry, and enables external overrides (plugins) without subclass proliferation.

This ADR finalizes the direction to eliminate legacy generator classes and move all telemetry production logic into composable emitters inside an `emission/` module.

## 2. Problem Statement
We must:
1. Support 3 flavors of GenAI telemetry with clear data capture semantics.
2. Allow vendor-specific span augmentation (Traceloop) without sacrificing semantic convention compatibility.
3. Allow a proprietary evaluation results aggregation event (Splunk) that replaces default per-result emission.
4. Guarantee that metrics and events are emitted in the active span context.
5. Provide a stable plugin/override mechanism and migration path.
6. Reduce maintenance burden (remove deep inheritance & redundant per-type generator classes).

## 3. Goals
| Goal | Description |
|------|-------------|
| G1 | Single orchestration path for all GenAI object emissions. |
| G2 | Remove `generators/*` concrete classes (retain thin compatibility shim temporarily). |
| G3 | Central ordering guarantees (span open for dependent emissions). |
| G4 | Flavor-based composition (span, span+metric, span+metric+event). |
| G5 | Extensible via entry point plugins (emitters & evaluators). |
| G6 | Traceloop: spans only + vendor attrs; still semconv-compliant. |
| G7 | Splunk: aggregated evaluation result event replaces default strategy. |
| G8 | Backward compatibility for current handler API. |
| G9 | Clear testing matrix & acceptance criteria. |

## 4. Non-Goals
- Streaming/partial evaluation emission (future consideration).
- Asynchronous batching of metrics/events.
- Full metrics parity for evaluation scores (can be gated later).

## 5. Key Concepts
### 5.1 Domain Types
Remain pure (no emission logic): `LLMInvocation`, `EmbeddingInvocation`, `ToolCall`, `EvaluationResult`, `Error`, and future extensions.

### 5.2 Emitters
Role-oriented small components implementing:
```python
class EmitterProtocol(Protocol):
    role: str  # span | metric | content_event | evaluation_result
    name: str
    handles: set[type]
    override: bool  # if true, replaces all defaults for its role when selected
    def start(self, obj, ctx): ...
    def finish(self, obj, ctx): ...
    def error(self, obj, err, ctx): ...
```
Only methods relevant to lifecycle need non-noop implementations per role.

### 5.3 Composite Orchestrator
`CompositeGenerator` (or `EmissionOrchestrator`) maintains ordered list of emitters and span lifecycle control. Ordering constraints:
1. span.start
2. (optional) content_event.start (input side) for `span_metric_event` flavor
3. metric.start (if any start-time metrics)
4. User completes invocation
5. metric.finish
6. content_event.finish (output, tool calls)
7. evaluation_result emission (start/finish per result OR aggregated) while span active
8. span.finish

Errors short-circuit after span.error → span.finish (no metrics/events/evaluations unless minimal input capture allowed).

### 5.4 Flavors
| Flavor | Metrics | Content Events | Content on Span | Evaluation Result Default |
|--------|---------|----------------|-----------------|---------------------------|
| span | No | No | Yes (if capture enabled) | Span attributes per result |
| span_metric | Yes | No | Yes | Span attrs + (optional) metrics |
| span_metric_event | Yes | Yes | Minimal summary only | Events per result (unless overridden) |

### 5.5 Data Capture Modes
`OTEL_GENAI_CAPTURE_CONTENT=none|input|output|full` determines inclusion of input/output. For `span_metric_event`, content is emitted as events; for others, as span attributes.

### 5.6 Plugin Overrides
Entry points:
- `opentelemetry_genai.generators` → emitters
- `opentelemetry_genai.evaluators` → evaluators

Override resolution:
1. Load defaults per role.
2. Load plugins.
3. Apply explicit `OTEL_GENAI_PLUGIN_OVERRIDES` (e.g. `span:traceloop,evaluation_result:splunk`).
4. Apply implicit convenience variable `OTEL_GENAI_SPAN_VENDOR=traceloop` if set.
5. For each role: if one or more selected emitters have `override=True`, keep first and drop others (log warning if >1 different override candidates).

### 5.7 Vendor Examples
- Traceloop Span Emitter: role=span, override or selected by vendor var; adds `traceloop.*` attrs + standard semconv attributes.
- Splunk Evaluation Emitter: role=evaluation_result, override; emits a single aggregated event `gen_ai.evaluations` summarizing all results.

### 5.8 Evaluation Flow
Evaluators run after invocation finish (success only):
```
results = [r for ev in evaluators for r in ev.evaluate(invocation)]
for r in results:
    composite.start(r)          # if per-result path
    composite.finish(r)
# OR aggregated emitter receives full list (implementation-defined)
```
Aggregation is enabled by an emitter declaring it handles list-of-results input or by override semantics.

## 6. Configuration
Environment variables:
- `OTEL_GENAI_FLAVOR=span|span_metric|span_metric_event`
- `OTEL_GENAI_CAPTURE_CONTENT=none|input|output|full`
- `OTEL_GENAI_PLUGIN_OVERRIDES=role:name[,role:name...]`
- `OTEL_GENAI_SPAN_VENDOR=semconv|traceloop`
- `OTEL_GENAI_EXPERIMENTAL_ATTRS=0|1`

Legacy vars (if any) map with deprecation warnings.

## 7. Migration & Refactor Plan
### Phase 1 (Completed / In Progress)
- Introduce composite/emission scaffolding alongside existing generators.
- Add ADR (this document) & update FEEDBACK.

### Phase 2
- Port span logic into `emission/span_emitter.py` (SemconvSpanEmitter).
- Implement metric & content event emitters; add flavor builder.
- Wire handler to use emission path; keep generator path behind feature flag `OTEL_GENAI_USE_LEGACY_GENERATORS=1` (temporary).

### Phase 3
- Implement evaluation result emitter(s) and evaluator integration.
- Add Splunk override stub (behind test double) for aggregated event.

### Phase 4
- Add plugin discovery + override resolution; tests with mock entry points.

### Phase 5
- Remove legacy `generators/` concrete classes; replace with deprecation stubs raising warning + delegating to emission orchestrator.
- Update `__all__` exports & docs.

### Phase 6
- Introduce external Traceloop & Splunk packages (or simulated fixtures) validating plugin contracts.

### Phase 7
- Clean up deprecated flags; remove compatibility layer after one minor release cycle.

## 8. Acceptance Criteria
| ID | Criteria |
|----|----------|
| A1 | All existing tests pass using emission path with legacy disabled. |
| A2 | Setting each flavor yields correct distribution of content (attrs vs events). |
| A3 | Metrics & events emitted only while invocation span active (verified via context assertions). |
| A4 | Error path emits span with error attrs, no metrics/events/evals (except allowed input capture). |
| A5 | Plugin override unit tests demonstrate: traceloop span override & splunk evaluation aggregation. |
| A6 | Legacy generator imports produce deprecation warning only, no functional divergence. |
| A7 | Documentation updated (README section + ADRs) and explains migration. |
| A8 | Codebase free of concrete per-type generator classes (except stubs). |

## 9. Ordering Guarantees (Detailed)
Start: span → (content event input) → (metric start)
Finish: metric finish → content event output → evaluation result(s) → span finish
Error: span error → (optional minimal input capture) → span finish

## 10. Testing Matrix
| Scenario | span | span_metric | span_metric_event |
|----------|------|-------------|-------------------|
| Input captured | Span attrs | Span attrs | Input event |
| Output captured | Span attrs | Span attrs | Output event |
| Metrics present | No | Yes | Yes |
| Eval results (default) | Span attrs | Span attrs + metrics (optional) | Events |
| Eval results (splunk) | Aggregated event | Aggregated event (+ metrics) | Aggregated event |
| Error path | Span only | Span only | Span only |

## 11. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Plugin conflict | Deterministic first-wins override + logged warning. |
| Performance overhead | Emitters minimal; early bail on roles not handling object type. |
| API churn for external adopters | Maintain stable handler interface; deprecate gradually. |
| Missing span context during emission | Central orchestrator ensures active span; test assertions. |
| Schema drift (vendor) | Contract tests + semconv compliance checklist. |

## 12. Open Questions
- Should evaluation aggregation optionally still set summary span attrs when overridden? (Default: yes.)
- Need standardized hashing algorithm for content summaries? (Chosen: SHA-256; configurable later.)
- Truncation thresholds for large content? (Add config: `OTEL_GENAI_CONTENT_TRUNCATE_BYTES`.)

## 13. Implementation Notes
- Use a lightweight `EmitterContext` dataclass carrying tracer, span, config, timing, and scratch fields (e.g. token counts).
- Provide `register_probe_emitter(test_recorder)` utility for ordering tests.
- Avoid coupling emitters to evaluation internals; evaluation results emitted as separate domain objects.

## 14. Deprecation Strategy
- First release with emission path: emit `DeprecationWarning` on import from `opentelemetry.util.genai.generators` pointing to ADR 0002.
- After one minor version: remove stubs (subject to semantic versioning policy; if <1.0, document in CHANGELOG).

## 15. Documentation Updates
- README: new section "Telemetry Flavors & Content Capture".
- Plugin author guide: roles, override semantics, minimal skeleton.
- FEEDBACK.md: link to ADR 0002 for final direction.

## 16. Example Env Configurations
Traceloop vendor span only:
```
OTEL_GENAI_FLAVOR=span
OTEL_GENAI_SPAN_VENDOR=traceloop
OTEL_GENAI_CAPTURE_CONTENT=input
```
Full stack with events & splunk evaluation aggregation:
```
OTEL_GENAI_FLAVOR=span_metric_event
OTEL_GENAI_CAPTURE_CONTENT=full
OTEL_GENAI_PLUGIN_OVERRIDES=evaluation_result:splunk
```

## 17. Minimal Plugin Skeleton (Span Override)
```python
# entry point group: opentelemetry_genai.generators = traceloop=traceloop_plugin:get_emitters
from opentelemetry.util.genai.interfaces import EmitterProtocol

class TraceloopSpanEmitter:
    role = "span"
    name = "traceloop"
    handles = {LLMInvocation}
    override = True
    def start(self, obj, ctx): ...  # start span + semconv attrs + traceloop.* vendor attrs
    def finish(self, obj, ctx): ...
    def error(self, obj, err, ctx): ...

def get_emitters():
    return [TraceloopSpanEmitter()]
```

## 18. Decision
Adopt emission-centric composite architecture; retire legacy generator class hierarchy behind deprecation shim; implement phased migration & plugin override mechanism as described.

---
END ADR 0002

