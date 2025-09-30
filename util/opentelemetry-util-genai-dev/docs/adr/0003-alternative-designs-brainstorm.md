# ADR 0003 (Exploratory): Alternative Emission Architecture Designs & Prototyping Paths

Status: Draft (Exploratory / Non-binding)  
Date: 2025-09-27  
Authors: GenAI Telemetry Working Group  
Related: ADR 0001, ADR 0002

## Purpose
This document captures a brainstorm of simpler / alternative architectural patterns for GenAI telemetry emission, emphasizing:
- Ease of onboarding for new contributors
- Minimal moving parts
- Progressive enhancement toward the chosen emission-centric model
- Fast prototyping for vendors (Traceloop, Splunk) and experimental evaluators

These are NOT final decisions; they inform future refactors or experimental branches.

---
## Design Option Matrix (Summary)
| ID | Name | Core Idea | Strengths | Trade-offs | Good For |
|----|------|----------|-----------|------------|----------|
| 1 | Functional Pipeline | Ordered list of functions | Easiest mentally | Hard to manage phases | Tiny demos |
| 2 | Two-Phase Pipeline | Separate start/finish lists | Clear lifecycle | Extra ceremony per phase | Core flavors |
| 3 | Declarative Role Map | Config maps roles → handlers | Transparent configuration | Indirection overhead | Config-driven builds |
| 4 | Event Bus | Publish/subscribe | Highly decoupled | Ordering guarantees weaker | Plugins, experiments |
| 5 | Hook Set (pytest style) | Named hook functions | Familiar pattern | Manual ordering if many | Plugin authoring |
| 6 | Middleware Chain | Each layer calls next() | Cross-cutting logic | Linear chain harder to branch | Logging, PII filters |
| 7 | Component Registry + Tags | Select by tags | Flexible filtering | Tag misuse risk | Multi-flavor selection |
| 8 | Data-Driven Spec | YAML/JSON phase spec | Reorder w/o code | Spec drift vs code | Rapid iteration |
| 9 | Single Emitter Interface | Duck-typed simple class | Minimal boilerplate | Can accumulate conditionals | Mid-scale systems |
| 10 | Hybrid (Phased + Bus) | Deterministic core + flexible periphery | Balanced extensibility | Two mechanisms complexity | Long-term evolution |

---
## Option 1: Functional Pipeline
A flat list of callables `(obj, ctx)` executed in order.
```python
Pipeline = [span_start, capture_input, emit_metrics, emit_eval_results]
for step in Pipeline:
    step(invocation, ctx)
```
Pros: zero overhead.  
Cons: No notion of start vs finish vs error phases.

---
## Option 2: Two-Phase Functional Pipeline
Explicit `start`, `finish`, `error` lists; still purely functional.
```python
class PhasedPipeline:
    def __init__(self):
        self.start, self.finish, self.error = [], [], []

pipeline.start.append(span_start)
pipeline.start.append(content_input)
pipeline.finish.append(metrics_finish)
pipeline.finish.append(content_output)
pipeline.finish.append(eval_emit)
pipeline.finish.append(span_finish)
```
Pros: Deterministic ordering.  
Upgrade path: wrap functions into objects later.

---
## Option 3: Declarative Role Map
Mapping expresses design intent; resolved into concrete functions.
```python
ROLE_HANDLERS = {
  'span': ['semconv_span', 'vendor_span'],
  'metrics': ['basic_metrics'],
  'content': ['attr_capture', 'event_capture'],
  'evaluation': ['per_result_eval'],
}
```
Pros: Readers see capabilities instantly.  
Cons: Indirection requires registry discovery step.

---
## Option 4: Event Bus (Observer)
Publish lifecycle events; subscribers react.
```python
bus.emit('invocation.start', obj=inv)
bus.emit('invocation.finish', obj=inv)
```
Pros: Maximum decoupling.  
Cons: Ordering and conflicts require additional policy.

---
## Option 5: Hook Set (pytest-like)
Named hooks; plugins implement subset.
```python
hooks: span_start, invocation_finish, invocation_error, emit_evaluation_results
```
Pros: Familiar open extension model.  
Cons: Harder to compose alternative flavors without more structure.

---
## Option 6: Middleware Chain
Each middleware wraps next.
```python
def middleware(obj, ctx, next):
    before(obj)
    next()
    after(obj)
```
Pros: Great for cross-cutting (timing, scrubbing).  
Cons: Linear; branching emission flows awkward.

---
## Option 7: Component Registry + Capability Tags
Components declare `tags`; orchestrator selects intersection with flavor requirements.
```python
component.tags = {'span', 'semconv'}
select(tags={'span','metrics'})
```
Pros: Unified filtering.  
Cons: Tag taxonomy creep risk.

---
## Option 8: Data-Driven Spec Interpreter
Phases and handlers externally defined (YAML/JSON) → runtime interpreter.
```yaml
phases:
  - id: span_start
    handlers: [semconv_span, vendor_span]
  - id: metrics_finish
    handlers: [basic_metrics]
  - id: eval_results
    handlers: [default_eval]
  - id: span_finish
    handlers: [finish_span]
```
Pros: Rapid iteration w/o code changes.  
Cons: Introspection/debugging harder.

---
## Option 9: Single Emitter Interface
Small class with optional lifecycle methods.
```python
class SimpleEmitter:
    def start(self, obj, ctx): pass
    def finish(self, obj, ctx): pass
    def error(self, obj, err, ctx): pass
```
Pros: Clean evolution path; subclassing optional.  
Cons: Conditional logic may accumulate inside large emitters.

---
## Option 10: Hybrid (Phased Pipeline + Event Bus)
Deterministic ordering for critical roles (span, metrics) + event bus for less-critical or experimental (evaluation formats, vendor attributes).

Pros: Balance of safety + flexibility.  
Cons: Two extension surfaces to document.

---
## Shared Context Pattern
```python
from dataclasses import dataclass, field

@dataclass
class EmitterContext:
    tracer: object
    span: object | None = None
    config: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=lambda: {'spans': [], 'metrics': [], 'events': []})
```

---
## Prototype Skeleton (Hybrid Example)
```python
# Build pipeline
pipeline = PhasedPipeline()
pipeline.start += [Span.start, Content.capture_input]
pipeline.finish += [Metrics.finish, Content.capture_output, Evaluation.finish, Span.finish]
pipeline.error += [Span.error]

# Event bus plugin
bus.on('span.start', vendor_enrich)
```

---
## Recommended Prototype Path
1. Start with Option 2 (Two-Phase Pipeline) for clarity.  
2. Layer in Option 4 (Event Bus) for optional vendor features.  
3. Migrate functions to Option 9 (SimpleEmitter) only if internal state accrues.  
4. If partner experimentation demands non-code ordering tweaks, introduce Option 8 (Spec Interpreter) as an experimental toggle.

---
## Demonstration Strategy
| Step | Artifact | Purpose |
|------|----------|---------|
| 1 | `examples/pipeline_demo.py` | Show flavor switching via config dict. |
| 2 | `tests/test_pipeline_flavors.py` | Assert distribution: span vs metrics vs events. |
| 3 | `tests/test_error_path.py` | Confirm no metrics/events on failure. |
| 4 | `tests/test_plugin_vendor.py` | Vendor span attribute injection via event bus. |
| 5 | `tests/test_eval_override.py` | Simulate Splunk aggregation emitter replacing default. |

---
## Extension Points Overview
| Extension Need | Simplest Path | Rationale |
|----------------|--------------|-----------|
| Add vendor span attrs | Event bus hook `span.start` | Zero coupling. |
| Replace eval emission | Swap function in `pipeline.finish` or register override in event bus | Minimal change surface. |
| Add new metric | Append new function to finish phase | Order preserved. |
| Instrument new invocation type | Add type-guard wrapper function | Avoid inheritance forest. |

---
## Evaluation of Options vs Current ADR 0002
| Criterion | ADR 0002 (Emitters) | Two-Phase Pipeline | Hybrid |
|-----------|---------------------|--------------------|--------|
| Onboarding complexity | Medium | Low | Medium |
| Ordering guarantees | Strong | Strong | Strong (core) |
| Plugin flexibility | Medium | Low (needs wrapping) | High |
| Testability (unit isolation) | High | High | High |
| Long-term scalability | High | Medium | High |

---
## Migration Thought Experiment
If current emitter system feels heavy for early adopters:
1. Implement internal emitters as plain functions first.  
2. Provide compatibility adapter turning functions into EmitterProtocol objects later.  
3. Preserve handler public API across both phases.

---
## Risks & Mitigations (Alternative Paths)
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Too many extension surfaces | Cognitive load | Document recommended layer per use-case. |
| Event bus misuse for ordering-critical logic | Race/order bugs | Lint rule / guideline: bus not for span lifecycle control. |
| Spec file divergence from code | Confusion | Generate spec from code; treat YAML as override only. |
| Function pipeline grows large | Readability | Group functions by role prefix or namespace module. |

---
## Open Questions
- Should we expose a public `register_phase_fn(phase, fn)` API or keep phases internal initially?
- Do we need transaction-like rollback if a finish phase fails? (Currently: best-effort logging.)
- Should evaluation aggregation be modeled as a transform step before emission rather than emitter replacement?

---
## Suggested Next Action
Create `examples/experimental/option2_pipeline_demo.py` implementing Option 2 + vendor enrichment via a micro event bus; add a short README snippet to compare output across flavors.

---
## Appendix: Minimal Code Snippets
### Two-Phase Pipeline Core
```python
class PhasedPipeline:
    def __init__(self):
        self.start, self.finish, self.error = [], [], []

    def add(self, phase, fn):
        getattr(self, phase).append(fn)
```

### Event Bus
```python
class EventBus:
    def __init__(self): self._subs = {}
    def on(self, event, fn): self._subs.setdefault(event, []).append(fn)
    def emit(self, event, **kw):
        for fn in self._subs.get(event, []): fn(**kw)
```

### Orchestrator
```python
class Orchestrator:
    def __init__(self, pipeline, bus):
        self.pipeline, self.bus = pipeline, bus

    def run(self, invocation, ctx):
        try:
            for fn in self.pipeline.start: fn(invocation, ctx, self.bus)
            # user work simulated externally
            for fn in self.pipeline.finish: fn(invocation, ctx, self.bus)
        except Exception as e:
            for fn in self.pipeline.error: fn(invocation, e, ctx, self.bus)
            raise
```

---
END ADR 0003 (Exploratory)

