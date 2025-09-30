# GenAI Telemetry Refactoring Snapshot (Phase 3.5 → 4)

Date: 2025-09-27 (Post legacy module removal)  
Status: Active development branch (pre-public stability).  
IMPORTANT: API is still experimental; breaking changes permitted without deprecation cycle.

---
## 1. Purpose
Snapshot of current architecture and the **remaining** focused refactor items after consolidating emitters and *removing* obsolete `generators/` and `emission/` module trees (no deprecation shims retained).

---
## 2. Current Architectural Snapshot (Updated)
| Area | State |
|------|-------|
| Domain Objects | `LLMInvocation`, `EmbeddingInvocation`, `ToolCall`, `EvaluationResult`, `Error`, message dataclasses & parts |
| Emission Model | Composition: `CompositeGenerator` + emitters (`SpanEmitter`, `MetricsEmitter`, `ContentEventsEmitter`) in `emitters/` package |
| Span Logic | Single `SpanEmitter` (`emitters/span.py`) using context manager (`start_as_current_span`) |
| Metrics | LLM: duration + token histograms; ToolCall: duration; Embedding: none (by design) |
| Content Events | LLM only (explicit exclusions for ToolCall & Embedding) |
| Handler | `TelemetryHandler` orchestrates lifecycle + evaluation |
| Protocol | Emitter contract: `start/finish/error` (+ optional `handles`) |
| Evaluations | LLM only (histogram + consolidated event + optional spans) |
| Environment Parsing | Centralized in `config.parse_env()` (generator flavor, capture mode, evaluation flags) |
| Attribute Constants | PARTIAL centralization; evaluation aggregation literals still inline |
| Legacy Paths | REMOVED (`generators/`, `emission/`, `emission_composite.py`, `GENERATORS.rst`, alias test) |
| Tests | Passing (mixed sequence, thread-safety, metrics, evaluation, tool call, embedding) |

---
## 3. Recent Work Completed
- Consolidated all emitters into `emitters/`.
- Removed obsolete legacy modules & alias test (no deprecation shims kept per request).
- README reflects emitter composition model.
- Test suite green after structural cleanup.

---
## 4. Remaining Gaps
| Gap | Status | Impact |
|-----|--------|--------|
| Full attribute constant centralization | PARTIAL | Harder to adapt to semconv churn (evaluation agg literals inline) |
| Evaluation aggregation constants (count/min/max/avg/names) | NOT DONE | Minor duplication & inconsistency risk |
| Evaluation generalization (Embeddings / ToolCall) | NOT STARTED | Limits reuse of evaluator infra |
| Evaluation span parenting documentation | PARTIAL | Ambiguity for span topology consumers |
| Attribute version / feature flag strategy | NOT STARTED | Harder to communicate semconv evolution |
| Semconv/version helper (expose schema URL programmatically) | NOT STARTED | Debug/observability convenience gap |
| Redaction / truncation policy guidance | NOT STARTED | Potential large payload risk |

(Items about alias / legacy path deprecation removed as obsolete.)

---
## 5. Design Principles (Stable)
1. Composition over inheritance.
2. Single handler façade; emitters pluggable.
3. Centralize config & attribute naming.
4. Keep surface minimal until divergence proven.
5. Iterate fast while semconv is incubating.

---
## 6. Definition of Done (Refined)
Done when:
- All `gen_ai.*` attribute keys (excluding tests) pulled from `attributes.py` (incl. evaluation aggregation keys).
- Evaluation span parenting decision documented (ADR or README note).
- README + emitter docs consistent (spot check passes).
- Optional: exported helper for semconv/schema version.

---
## 7. Implementation Queue (Ordered)
1. Add remaining evaluation aggregation constants & replace literals in handler.
2. Introduce operation value fallback constants (`tool_call`, `embedding`) if desired for consistency.
3. Document evaluation span parenting choice (link-only vs parent/child) and rationale.
4. Provide semconv/schema version helper (optional).
5. Add attribute versioning / churn guidance (ATTRIBUTES.rst or README section).
6. Add redaction guidance & potential future hook (stretch).
7. Explore evaluator generalization for embeddings & tool calls (stretch).

---
## 8. Risk & Mitigation
| Risk | Mitigation |
|------|-----------|
| Attribute churn | Complete constant centralization. |
| Large content payloads | Add redaction guidance & future hook placeholder. |
| Span topology misunderstanding | Document parenting/link rationale. |
| Evaluator scope pressure | Plan phased generalization; keep interface stable. |

---
## 9. Progress Tracker
```
Centralize remaining literals:    PENDING
Evaluation agg constants:         PENDING
Evaluation span parenting doc:    PENDING
Semconv version helper:           PENDING (optional)
Attribute versioning note:        PENDING
Redaction guidance:               PENDING (stretch)
Evaluator generalization:         PENDING (stretch)
```

---
## 10. Notes
Legacy generator/emission modules fully removed to avoid dual import paths. Any downstream code must migrate to `opentelemetry.util.genai.emitters` imports.

---
End of snapshot.
