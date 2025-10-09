# OpenTelemetry GenAI Utility – Implementation Findings

Document date: 2025-10-08
Scope: `util/opentelemetry-util-genai-dev` package (core + emitters + evaluators). Compares actual implementation with the reference architecture in `README.architecture.md` and high-level snapshot in `../README.architecture.packages.md`.

---
## Summary
The implementation broadly aligns with the intended layered design (Types → Handler → CompositeEmitter → Emitters / Evaluation Manager). Key divergences concern:

* Naming / protocol drift (`TelemetryHandler` vs proposed `Handler`; `EmitterMeta.role` values differ from documented category names; `MetricsEmitter.role = "metric"` vs expected `metrics`).
* Category names / ordering semantics differ slightly from the architecture doc (implementation uses `span`, `metrics`, `content_events`, `evaluation` with explicit start/end ordering arrays; architecture text implies fan-out with some different phrasing and capability flags).
* Evaluation results aggregation: implementation aggregates only when env flag set; architecture doc matches this but does not mention dual emitters (metrics + events) always registered.
* Environment variable grammar: supports additional directives (`prepend`, `replace-same-name`) and a consolidated baseline selector `OTEL_INSTRUMENTATION_GENAI_EMITTERS` (values: `span`, `span_metric`, `span_metric_event`, plus extras) not fully described in current architecture README.
* Content capture gating depends on experimental semantic convention opt-in (`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`); doc currently presents capture variables w/o experimental caveat.
* Invocation types extended (Workflow, AgentInvocation, Task, EmbeddingInvocation, ToolCall) with additional metrics; architecture snapshot partially anticipates but does not detail metrics instrumentation for agentic types.
* Missing `EvaluationResults` aggregate class (architecture document references an aggregate container) – implementation forwards raw `list[EvaluationResult]`.
* No explicit `CompositeEmitter.register_emitter` public API (architecture describes one); implementation relies on env parsing + spec registration but lacks runtime chain mutation helpers beyond instantiation.
* Evaluator plugin system more elaborate than described (plan parsing, per-type metric configuration), but lacks an abstraction for aggregated vs non-aggregated result object.
* Some TODO / compatibility code (e.g. legacy event names, traceloop compat paths) not captured in architecture doc.

---
## Detailed Findings

### 1. Types (`types.py`)
| Aspect | Implementation | Architecture Expectation | Finding |
|--------|----------------|--------------------------|---------|
| Base class name | `GenAI` dataclass | `GenAIInvocation` conceptually | Minor naming divergence (fine if documented) |
| Semantic attribute surfacing | Dataclass fields with `metadata{"semconv"}` + `semantic_convention_attributes()` | Matches spec | ✅ |
| Message modeling | `InputMessage` / `OutputMessage` with `parts` (Text / ToolCall / ToolCallResponse / Any) | Doc mentions role/content parts | ✅ |
| Additional invocation types | `EmbeddingInvocation`, `Workflow`, `AgentInvocation`, `Task`, `ToolCall` | Architecture lists prospective types (Agent, Workflow, Step/Task) | ✅ (needs README refresh) |
| Evaluation aggregate | Only `EvaluationResult` (atomic) | `EvaluationResults` aggregate class referenced | Missing class or doc update required |
| Error representation | `Error(message, type)` | Architecture brief mention only | ✅ |
| Token fields for embedding | `input_tokens` only; no output tokens | Acceptable (embedding output token concept ambiguous) | Note for doc |

### 2. Interfaces / Protocols (`interfaces.py`)
* `EmitterProtocol` includes `on_error` (architecture simplified protocol omitted this) and `on_evaluation_results(results, obj=None)` returns `None` – doc should reflect extra hook.
* `EmitterProtocol` does not define capability flags (`emits_spans`, etc.) – remove or document as deferred.
* `EmitterMeta` carries `role`, `name`, `override` plus `handles(obj)` predicate. Architecture describes categories & invocation type filtering; actual filtering implemented by dynamically wrapping `handles` in configuration layer, not inherent to protocol.

### 3. Handler (`handler.py`)
* Named `TelemetryHandler` (vs `Handler`). Provides granular per-type start/stop/fail plus generic `start/finish/fail` dispatchers. Architecture README should adopt this or specify alias.
* Content capture refresh: `_refresh_capture_content()` inspects env each LLM start; architecture envisioned central config at initialization – highlight dynamic refresh behavior.
* Completion callbacks implemented; evaluation manager auto-registered only if evaluators present.
* Evaluation emission method signature: `evaluation_results(invocation, results: list[EvaluationResult])` (no EvaluationResults wrapper).

### 4. Emitters – Spec & Configuration
| Component | Implementation | Difference / Issue |
|-----------|----------------|--------------------|
| Spec class | `EmitterSpec(name, category, factory, mode, after, before, invocation_types)` | Architecture spec fields differ: uses `kind`, `position` with before/after semantics; doc must sync to actual names. |
| Modes supported | `append` (default), `replace-category`, `prepend`, `replace-same-name` | Architecture lists same + some textual differences; confirm naming. |
| Ordering hints | `after`, `before` sequences present on spec but unused in `build_emitter_pipeline` ordering logic (no explicit resolution code) | Potential gap: `after` / `before` not applied; doc or code update needed. |
| Category overrides | Env var parsing yields `CategoryOverride(mode, emitter_names)`; directives: `append`, `prepend`, `replace`, `replace-category`, `replace-same-name` | Architecture examples use `replace-category:` prefix – consistent; need to document accepted aliases (`replace:`). |
| Programmatic registration | No public `register_emitter` on `CompositeEmitter` (only `add_emitter` without ordering/mode handling) | Missing or intentionally deferred; document limitation. |
| Invocation type filtering | Implemented by wrapping `.handles` via dynamic method patch in `_instantiate_category` | Implementation detail differs from design’s declarative `invocation_types` filter; should document. |
| Content capture gating | Controlled by `Settings.capture_messages_mode`, `capture_messages_override`, plus experimental mode check | Architecture lacks experimental stable/unstable semantics – update needed. |

### 5. Emitters – Individual
* `SpanEmitter`: Implements content capture for input and output messages; enumerates request functions; adds supplemental filtered `attributes` keys restricted to semantic + allowed extras. Adds system instructions as `gen_ai.system.instructions` attribute (not in architecture doc – add).
* `MetricsEmitter`: Role string is `metric` (singular) but category configured as `metrics`; potential mismatch for introspection (only used by composite lists). Should standardize or clarify role vs category concept.
* `ContentEventsEmitter`: Currently emits only a single event summarizing an entire LLM invocation (NOT per message). Architecture doc originally described potentially one event per message; adjust doc or implementation. Commented-out code hints at future agent/workflow events.
* `EvaluationMetricsEmitter` and `EvaluationEventsEmitter` are both always registered; architecture doc envisioned possibly a single evaluation emitter chain – update.
* Missing vendor emitters (Traceloop, Splunk) in this dev package – expected to come from separate packages; document absence and extension points.

### 6. CompositeEmitter (`composite.py`)
* Enforces start ordering (`span`, `metrics`, `content_events`) and end ordering (`evaluation`, `metrics`, `content_events`, `span`). Architecture described span first on start and last on end – consistent; evaluation ordering should be clarified (evaluation emitters do not receive lifecycle end events except via explicit code path inside dispatch – design doc should reflect evaluation results are dispatched separately, plus evaluation emitters ALSO receive on_end/on_error per dispatch ordering?).
* Evaluation emitters only receive `on_evaluation_results`; they are also iterated in `_CATEGORY_END_ORDER` so they receive `on_end` / `on_error` (currently `_CATEGORY_END_ORDER` begins with `evaluation`). Architecture doc should clarify this hook (flush semantics) or code should drop them if not required.

### 7. Configuration (`config.py` + env vars)
* Baseline multi-token env var `OTEL_INSTRUMENTATION_GENAI_EMITTERS` drives enabling of span/metrics/content events – not fully documented in architecture README.
* Category-specific overrides parse directives with optional colon prefix (`replace:SemanticConvSpan,TraceloopSpan`). Accepts synonyms (`replace`, `replace-category`). Additional directive `replace-same-name` supported though not documented earlier.
* Legacy capture compatibility via `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` still influences handler refresh; architecture doc treats capture controls more simply.
* Evaluation sample rate env var `OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE` not described in architecture doc.
* Legacy evaluation event flag `OTEL_GENAI_EVALUATION_EVENT_LEGACY` not mentioned.

### 8. Evaluation Manager
* Sampling uses Span trace ID with `TraceIdRatioBased`; architecture doc did not mention sampling; add section.
* Complex evaluator config grammar implemented (supports per-metric options) – architecture doc only lightly sketches grammar; ensure updated examples include options syntax (already present in env var docstring).
* Aggregation implemented as boolean flag; architecture doc consistent but lacks detail that evaluation metrics emitter and events run regardless of aggregation (list vs per-bucket emission difference).
* Manager flags invocation with attribute `gen_ai.evaluation.executed` – not documented.

### 9. Missing / Deferred Features
| Feature | Architecture Status | Implementation Status | Action |
|---------|---------------------|------------------------|--------|
| `EvaluationResults` container class | Described | Not implemented | Implement class or amend docs |
| Programmatic emitter chain mutation API (`register_emitter` with position) | Described | Only `add_emitter(category, emitter)` simple append | Implement or update docs |
| Ordering hints (`position="after:Name"`) | Described | Spec has `after`/`before` but no resolution logic | Implement resolution or remove from doc |
| Capability flags (`emits_spans`, etc.) | Described | Not implemented | Remove from doc or add flags |
| Async emitters | Explicitly out of scope | Not implemented | ✅ |
| Dynamic hot-swap reconfig | Deferred | Not implemented (except capture refresh partial) | ✅ |

### 10. Potential Bugs / Risks
1. `after` / `before` fields in `EmitterSpec` unused – user expectations unmet if third-party supplies ordering hints.
2. `MetricsEmitter.role = "metric"` may cause confusion; composite categories use plural name.
3. `ContentEventsEmitter` excludes agent/workflow/task events (commented out) – mismatch with potential future design; silent omission might surprise users.
4. Content capture silently disabled unless experimental semconv opt-in env var includes `gen_ai_latest_experimental`; architecture doc could mislead users expecting capture.
5. Evaluation sampling relies on presence of `invocation.span` and its context; if spans disabled but evaluations desired, sampling may degrade (manager logs debug). Consider fallback to random sampling when no trace id.
6. `_refresh_capture_content` mutates emitters mid-flight; race conditions unlikely (single-thread instrumentation typical) but not guarded by locks.
7. `EvaluationMetricsEmitter` assumes histogram creation succeeded; missing defensive null checks (low risk).
8. Potential attribute duplication: `SpanEmitter` first applies invocation semantic attrs then calls `_apply_gen_ai_semconv_attributes` again in finish; benign but redundant.
9. Legacy evaluation event emission controlled by `OTEL_GENAI_EVALUATION_EVENT_LEGACY` – if accidentally set, could double event volume; consider documenting rate impact.

### 11. Documentation Gaps To Address in `README.architecture.md`
* Rename / acknowledge `TelemetryHandler` vs `Handler`.
* Update emitter spec field names and supported directives.
* Clarify evaluation emitters (metrics + events) always registered; how aggregation affects only batching, not emitter presence.
* Add sampling explanation + env var for evaluation sample rate.
* Clarify experimental gating for content capture variables.
* Note absence of `EvaluationResults` class (or add it) and current list-based API.
* Add new agentic types + associated metrics histograms.
* Document implementation detail of invocation type filtering (dynamic wrapping of `handles`).
* Clarify single-event content emission vs per-message (and rationale).
* Mention legacy flags (`OTEL_GENAI_EVALUATION_EVENT_LEGACY`, legacy capture envs) and compatibility posture.

### 12. Recommendations
1. Decide whether to implement ordering resolution for `after`/`before` or remove from spec to prevent confusion.
2. Either rename `MetricsEmitter.role` to `metrics` or explicitly state role is informational and categories are separate.
3. Introduce optional `EvaluationResults` dataclass wrapper for future aggregated metadata (e.g., evaluator count, latency) – low effort.
4. Provide explicit helper API to register emitters programmatically with mode/ordering semantics (thin layer invoking internal registry logic) to match documented extensibility.
5. Enhance documentation with experimental gating explanation for content capture to prevent user confusion.
6. Add unit tests around category overrides (prepend, replace-same-name) and ensure negative cases (unknown emitter) log warnings (currently partial).
7. Consider fallback random sampling in evaluation manager when no trace ID present, to maintain sample rate consistency.
8. Consolidate duplicate attribute application in `SpanEmitter` to reduce overhead (micro-optimization).

---
## Appendix: Environment Variables (Observed vs Documented)

| Variable | Implemented | Doc Status (current) | Action |
|----------|-------------|----------------------|--------|
| OTEL_INSTRUMENTATION_GENAI_EMITTERS | Baseline + extras (span_metric_event) | Partially (older doc) | Update doc with baseline modes |
| OTEL_INSTRUMENTATION_GENAI_EMITTERS_<CATEGORY> | Supports append/prepend/replace/replace-category/replace-same-name | Partially (replace-category examples only) | Expand docs |
| OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES | span/events/both/none + experimental gating | Mentioned (no gating) | Add experimental note |
| OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT(_MODE) | Legacy fallback | Not emphasized | Mark legacy |
| OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS | Full grammar with per-type metric(options) | Summarized | Align examples |
| OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION | Bool | Mentioned | ✅ |
| OTEL_INSTRUMENTATION_GENAI_EVALS_INTERVAL | Poll interval | Omitted in architecture | Add |
| OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE | Trace-based sampling ratio | Omitted | Add |
| OTEL_GENAI_EVALUATION_EVENT_LEGACY | Emit legacy evaluation event format | Omitted | Add |

---
## Change Log (for this findings doc)
* v1 (2025-10-08): Initial audit results.

---
End of implementation findings.
