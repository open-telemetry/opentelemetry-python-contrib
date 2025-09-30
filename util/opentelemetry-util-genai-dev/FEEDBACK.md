# opentelemetry-util-genai Architectural Feedback

Date: 2025-09-24
Scope: Review of proposed class/package structure, extensibility goals, and risk of premature abstraction.

## 1. High-Level Assessment
Your strategic goals (decoupling instrumentation from emission, supporting multiple telemetry "flavors", enabling evaluators, and backward compatibility) are solid. The main risk is over-expanding class hierarchies and package fragmentation before real divergence of behavior justifies them.

Lean principle: Keep the core minimal, composable, and data‑model centric; add layers only once ≥2 concrete implementations demand differentiation.

## 2. Current vs Proposed
Current implementation: A simple `SpanGenerator` plus a handler that creates spans for `LLMInvocation`. This is easy to maintain and fast to evolve.

Proposed design introduces:
- Deep inheritance: `BaseGenerator` → `BaseSpanGenerator` → `LLMInvocationSpanGenerator`, etc.
- Per GenAI type × per telemetry type classes (Cartesian growth).
- Multiple packages for generators, evaluators, decorators, translators early.
- Separate handlers per data type.

Risk: Boilerplate explosion, slower iteration during a still-moving semantic conventions (semconv) phase.

## 3. Recommended Lean Core (MVP)
Core building blocks to stabilize first:
1. Data types (`LLMInvocation`, `EmbeddingInvocation`, `ToolCall`, `EvaluationResult`, `Error`) as plain dataclasses / pydantic-lite (no telemetry logic inside).
2. A single `Generator` protocol: `start(obj)`, `finish(obj)`, `error(obj, err)`.
3. `CompositeGenerator` that fans out calls to a list of emitters (SpanEmitter, MetricEmitter, EventEmitter) — composition over inheritance.
4. One `TelemetryHandler` orchestrating lifecycle + env-based configuration + optional evaluation triggering.
5. `Evaluator` protocol: `evaluate(obj) -> list[EvaluationResult]`.
6. Optional plugin discovery via entry points (defer actual external packages until needed).

## 4. What to Defer (Premature / Overengineered Now)
| Area | Why Defer | Lean Alternative |
|------|-----------|------------------|
| Deep inheritance tree of Base* classes | Adds cognitive load without behavior differences | Flat protocol + small emitters |
| Per telemetry type + per GenAI type classes | Creates boilerplate (Span+Metric+Event × N types) | Single emitter branches on `isinstance` |
| Multiple packages (traceloop, splunk, decorators) now | Release & version coordination overhead | Keep in-core or external after API stabilizes |
| Hooks `_on_before_* / _on_after_*` | YAGNI until cross-cutting concerns exist | Add a middleware list later |
| Separate handlers (LLMInvocationTelemetryHandler, etc.) | API surface bloat | Single handler + optional convenience wrappers |
| Dedicated evaluation handler | Duplicates lifecycle logic | Use existing handler post-finish phase |

## 5. Env & Config Suggestions
Simplify and future-proof variable names:
- `OTEL_GENAI_FLAVOR=span|span_metrics|span_metrics_events`
- `OTEL_GENAI_CAPTURE_CONTENT=none|input|input_output|full`
- `OTEL_GENAI_EVALUATORS=deepeval,ragas`
- `OTEL_GENAI_EXPERIMENTAL_ATTRS=1` (gate non-stable attrs)

Keep parsing centralized (single config object) so new strategies don’t scatter env lookups.

## 6. Semantic Conventions Strategy
- Pin semconv version explicitly and expose via `get_semconv_version()`.
- Maintain a mapping module for attribute names (avoid spreading literals) — easier churn handling.
- Introduce feature flag for experimental attributes.
- Document attribute changes per release (ADD / RENAME / DEPRECATE table).

## 7. Evaluation Architecture Guidance
Lifecycle:
```
start(invocation)
... user action ...
finish(invocation)
if evaluations enabled:
    for ev in evaluators:
        results = ev.evaluate(invocation)
        for r in results:
            generator.start(r); generator.finish(r)
```
No need for a separate evaluation handler unless you require streaming or asynchronous batching.

## 8. Decorators Layer
Keep decorators lightweight sugar around building domain objects and calling the handler. Defer publishing a dedicated decorators package until patterns stabilize. Provide a helper like:
`wrap_llm_call(fn, handler, model=..., capture_input=True, capture_output=True)`.

## 9. Backward Compatibility (Traceloop)
Use an adapter pattern:
- `TraceloopAdapter(traceloop_obj) -> LLMInvocation`
Then feed into existing handler & generators. Avoid special generator subclasses early.

## 10. Plugin / Extension Loading
Phase-in plan:
- Phase 1: Hard-coded internal emitters.
- Phase 2: Entry point discovery (e.g., `opentelemetry_genai.generators`).
- Phase 3: External plugin packages once at least one real consumer emerges.

## 11. Versioning & Stability Signaling
- Expose `__telemetry_api_version__` in package root.
- Emit a one-time warning if API labeled experimental (suppressible by env var).
- Provide clear upgrade notes with attribute diffs.

## 12. Decision Heuristics (Litmus Test)
Before adding a new abstraction ask:
1. Does it remove duplication across ≥2 concrete implementations NOW?
2. Is there an external request that needs this seam?
3. Will removing it later be a breaking change? (If yes, keep it out until confidence is higher.)

If answers: (No / Not yet / Yes) → Defer.

## 13. Proposed Interfaces (Illustrative Sketch)
```python
class Generator(Protocol):
    def start(self, obj: Any): ...
    def finish(self, obj: Any): ...
    def error(self, obj: Any, err: Error): ...

class Evaluator(Protocol):
    def evaluate(self, obj: Any) -> list[EvaluationResult]: ...

class CompositeGenerator:
    def __init__(self, emitters: list[Generator]): self._emitters = emitters
    def start(self, obj):
        for e in self._emitters: e.start(obj)
    def finish(self, obj):
        for e in self._emitters: e.finish(obj)
    def error(self, obj, err):
        for e in self._emitters: e.error(obj, err)

class TelemetryHandler:
    def __init__(self, generator: Generator, evaluators: list[Evaluator]): ...
    def start_llm(self, inv): self.generator.start(inv)
    def stop_llm(self, inv):
        self.generator.finish(inv)
        for ev in self.evaluators:
            for res in ev.evaluate(inv):
                self.generator.start(res); self.generator.finish(res)
    def fail_llm(self, inv, err): self.generator.error(inv, err)
```

## 14. Evolution Roadmap
| Phase | Goal | Deliverables |
|-------|------|--------------|
| 0 | Current baseline | Span emitter only |
| 1 | Composite architecture | Introduce `CompositeGenerator` + config parsing |
| 2 | Evaluations MVP | Evaluator protocol + dummy evaluator + emission of results as spans/events |
| 3 | Metrics/Events opt-in | Add metric & event emitters behind flavor flag |
| 4 | Embeddings / ToolCalls | Extend data types; reuse same handler |
| 5 | Plugin discovery | Entry point loading; doc for third parties |
| 6 | Traceloop adapter | External translator package or internal adapter |
| 7 | Vendor-specific flavor | Only if real divergence; otherwise keep config-driven |
| 8 | Hardening & Semconv changes | Attr mapping + upgrade guide |

## 15. Immediate Actionable Steps
1. Add a `CompositeGenerator` (even if wrapping one span emitter today) to future-proof API without inheritance commitment.
2. Centralize environment parsing into a `config.py` returning a frozen settings object.
3. Introduce `Evaluator` protocol + stub implementation (returns empty list) to anchor extension surface.
4. Consolidate span attribute name mapping in one module (reduces churn risk).
5. Write an ADR: "Adopt composition for GenAI telemetry generation; defer deep subclassing." and link to this feedback.
6. Refactor existing handler (if multiple) into a single orchestrator with type-dispatch table (optional convenience wrappers remain).

## 16. What NOT To Implement Yet
- `BaseMetricGenerator`, `BaseEventGenerator` with placeholder hooks.
- Separate handler classes per GenAI type.
- Multi-package external splits (deepeval, splunk) until extension API is proven.
- Hook lattice (`_on_before_*`)—substitute later with a simple middleware list if needed.

## 17. Summary
Proceed with a minimal, composable core (data types + single composite generator + handler + evaluator protocol). Defer class explosions and multi-package fragmentation until real, measurable divergence appears. This keeps iteration speed high, lowers cognitive load, and reduces risk of locking into an inflexible inheritance design while semantic conventions are still stabilizing.

## 18. Optional Next Additions (If You Want Quick Wins)
- Add a simple logging emitter (debug-level) to validate composite fan-out.
- Provide a sample evaluator that calculates prompt/response token delta or length-based heuristic, just to exercise the pipeline.
- Include an internal metrics counter (number of invocations, failures) to dogfood metric emission design later.

---
Feel free to iterate on any section; this document can evolve into an ADR reference.

