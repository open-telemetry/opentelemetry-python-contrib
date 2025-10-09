# Evaluation Results Refactoring

Refactor plan for aligning `EvaluationResults` emission across:

1. `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/evaluation.py`
   - Adopt OpenTelemetry Generative AI Semantic Conventions for evaluation events.
   - Emit **one OTel event per evaluation result** using the canonical event name: `gen_ai.evaluation.result`.
2. `util/opentelemetry-util-genai-emitters-splunk/src/opentelemetry/util/genai/emitters/splunk.py`
   - Emit **one aggregated Splunk-style event** containing the *conversation (input/output/system instructions) + all evaluation results* + evaluated span attributes for the invocation.
   - Emit **one metric measurement per evaluation result** using the metric name pattern: `gen_ai.evaluation.result.<metric_name>` (e.g. `gen_ai.evaluation.result.bias`).
   - Initial numeric score range normalized to **[0, 1]**.

---
## 1. Background
Instrumentation-side ("online") evaluations use an evaluator (often an LLM-as-a-judge) to assess the semantic quality of GenAI outputs (e.g. bias, relevance, toxicity, coherence). Developers need both:

- **Aggregatable KPIs** (scores & labels) for dashboards / alerting.
- **Context-rich exemplars** (input/output + evaluation reasoning) for root-cause and quality improvement workflows.

Current state:
- The dev util emitter already produces one event per evaluation result, but uses a non-spec event name (`gen_ai.evaluation`) and a body structure diverging from the semantic conventions.
- The Splunk emitter only emits conversation-centric events; no consolidated evaluation event or per-metric measurements yet.

---
## 2. Goals / Scope
| Area | In Scope | Out of Scope |
|------|----------|--------------|
| OTel semantic alignment | Update event name + attribute keys to match `event.gen_ai.evaluation.result` spec | Adding new experimental attributes not in current spec |
| Metrics | Per-metric emission in Splunk emitter; histogram/gauge choice TBD | Cross-process correlation enrichment |
| Aggregated event (Splunk) | Single event with conversation + all evaluation results | Multi-event replay pipelines |
| Score normalization | Enforce / document [0,1] expectation in Splunk metrics | Automatic re-scaling of arbitrary evaluator scales (warn only) |
| Error reporting | Map evaluation error into `error.type` when present | Rich stack traces |

---
## 3. Semantic Conventions (Reference)
Spec: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-events.md#event-eventgen_aievaluationresult

Required / conditional attributes for `gen_ai.evaluation.result`:
- `gen_ai.evaluation.name` (string, REQUIRED)
- `gen_ai.evaluation.score.value` (double, when applicable)
- `gen_ai.evaluation.score.label` (string, when applicable)
- `gen_ai.evaluation.explanation` (string, recommended)
- `gen_ai.response.id` (recommended when parent span id not available)
- `error.type` (conditional)

Parenting: SHOULD be parented to the GenAI operation span when available; fallback to response id.

---
## 4. Proposed Emission Models
### 4.1 Dev Util (Spec-Compliant) Event Model
One event per evaluation result.

**Event name**: `gen_ai.evaluation.result`

**Attributes (flat)**:
```
{
  "gen_ai.evaluation.name": "bias",
  "gen_ai.evaluation.score.value": 0.73,
  "gen_ai.evaluation.score.label": "medium",
  "gen_ai.evaluation.explanation": "Mild national stereotype detected.",
  "gen_ai.response.id": "chatcmpl-abc123",         // when available
  "gen_ai.operation.name": "evaluation",             // (kept for operational filtering - optional to revisit)
  "gen_ai.request.model": "gpt-4o",                  // contextual enrichment
  "gen_ai.provider.name": "openai",                  // contextual enrichment
  "error.type": "EvaluatorTimeout"                   // only if present
}
```
No body required unless we choose to include supplemental evaluator attributes; per spec, explanation is an attribute (not body). Existing custom attributes may be nested behind a namespaced key if retention is desired (e.g. `gen_ai.evaluation.attributes.*`).

### 4.2 Splunk Aggregated Event Model
Single event emitted **after invocation + evaluations complete**.

**Event name**: `gen_ai.splunk.evaluations` (distinct namespace to avoid confusion with spec-compliant per-result events; includes conversation + all evaluations).

**Body** structure example:
```jsonc
{
  "conversation": {
    "inputs": [ { "role": "user", "parts": [{"type": "text", "content": "Weather in Paris?"}] } ],
    "outputs": [ { "role": "assistant", "parts": [{"type": "text", "content": "Rainy and 57°F"}], "finish_reason": "stop" } ],
    "system_instructions": [ {"type": "text", "content": "You are a helpful assistant."} ]
  },
  "span": { "trace_id": "...", "span_id": "...", "gen_ai.request.model": "gpt-4o" },
  "evaluations": [
    {
      "name": "bias",
      "score": 0.15,
      "label": "low",
      "range": "[0,1]",
      "explanation": "No subjective bias detected",
      "judge_model": "llama3-8b"
    },
    {
      "name": "toxicity",
      "score": 0.02,
      "label": "none",
      "range": "[0,1]",
      "explanation": "No explicit or implicit toxicity",
      "judge_model": "tox-detector-v2"
    }
  ]
}
```
**Attributes**:
```
{
  "event.name": "gen_ai.splunk.evaluations",
  "gen_ai.request.model": "gpt-4o",
  "gen_ai.provider.name": "openai",
  "gen_ai.operation.name": "evaluation"
}
```

### 4.3 Splunk Metrics
For each evaluation result (after normalization to [0,1]):
- Metric name: `gen_ai.evaluation.result.<metric_name>`
- Value: numeric score (float)
- Attributes (recommended low-cardinality):
  - `gen_ai.evaluation.score.label`
  - `gen_ai.request.model`
  - `gen_ai.provider.name`
  - `gen_ai.evaluation.name` (if not implied by metric name; may be redundant—decide based on backend grouping needs)

Open question: Histogram vs Gauge.
- If tracking distribution: Histogram.
- If tracking latest per-dimension: Gauge.
Initial proposal: reuse existing histogram emitter for spec layer; Splunk-specific layer emits one gauge per metric (OR keeps histogram if already configured). Documented as a decision point.

---
## 5. Normalization Rules ([0,1])
If evaluator returns a score outside [0,1]:
1. If it provides an original `range` (e.g. `[0,4]`), attempt linear normalization: `norm = raw / max_range` (assuming min=0).
2. If ambiguous, log debug + skip metric emission (still include raw in aggregated event for transparency).
3. Add optional config toggle: `allow_out_of_range` (default False) to record raw values anyway.

---
## 6. Required Code Changes
### 6.1 util-genai-dev `evaluation.py`
- Rename emitted event name from `gen_ai.evaluation` -> `gen_ai.evaluation.result`.
- Move `explanation` from event body into attribute `gen_ai.evaluation.explanation` per spec.
- Rename/ensure attributes:
  - `GEN_AI_EVALUATION_NAME` -> maps to `gen_ai.evaluation.name` (confirm constant name).
  - Add constant for `gen_ai.evaluation.score.value` (currently `GEN_AI_EVALUATION_SCORE_VALUE`).
  - Add constant for `gen_ai.evaluation.explanation` (if missing).
- Remove custom body wrapper unless additional non-spec attributes are present; if so, nest under `gen_ai.evaluation.extra`.
- Ensure parent span context (span_id/trace_id) provided via SDK event API.
- Add tests asserting exact attribute keys and event name.

### 6.2 Add / Update Attribute Constants
Check `..attributes` module for missing constants:
- `GEN_AI_EVALUATION_EXPLANATION = "gen_ai.evaluation.explanation"`

### 6.3 Splunk Emitter (`splunk.py`)
- Add new emitter `SplunkEvaluationResultsEmitter`.
- Accumulate evaluation results (hook into `on_evaluation_results`).
- Emit single combined event at `on_end` (depends if evaluation results arrive before end—if asynchronous, add flush logic).
- Structure body per section 4.2.
- Implement optional normalization helper.
- Emit per-result metric via provided meter (inject via factory context):
  - Accept meter or metric recording function in constructor.
  - Derive metric instrument names dynamically.
- Guard against high-cardinality attributes (avoid passing free-form reasoning to metrics; only include reasoning in event body).

### 6.4 Context Handling
- In aggregated event, include span attributes & IDs (trace_id, span_id) already present in conversation emitter—reuse logic (refactor shared helper?).
- Ensure conversation capture honors existing `capture_event_content` toggle.

### 6.5 Tests
Add tests in both packages:
- Per-result event emission spec compliance.
- Aggregated Splunk event contains all evaluations and conversation arrays.
- Metric names correctly generated; invalid names sanitized (non-alphanumeric -> underscore).
- Normalization logic: raw 3.0 with range `[0,4]` => 0.75.
- Out-of-range without range => metric skipped.

### 6.6 Backward Compatibility
- Provide feature flag `OTEL_GENAI_EVALUATION_EVENT_LEGACY=1` to retain old event name (`gen_ai.evaluation`) for transition (optional; decide based on adoption risk).
- Document deprecation timeline in CHANGELOG section.

---
## 7. Migration / Upgrade Notes
| Change | Action for Integrators |
|--------|------------------------|
| Event name changed | Update log/event processors & queries to new `gen_ai.evaluation.result` |
| Explanation attribute relocation | Update queries to look at `gen_ai.evaluation.explanation` instead of event body |
| Aggregated Splunk evaluation event added | Adjust ingestion pipeline to parse `body.evaluations[]` |
| Per-metric metrics added | Create dashboards using pattern `gen_ai.evaluation.result.*` |

---
## 8. Open Questions / Decisions Pending
| Topic | Question | Proposed Default |
|-------|----------|------------------|
| Metric instrument type | Histogram vs Gauge | Histogram (consistency) |
| Include `gen_ai.operation.name` on events | Spec doesn't require; keep for filters? | Keep for now |
| Legacy event compatibility | Needed? | Provide opt-in env var |
| Normalization when min != 0 | Rare now; handle later | Assume min=0, log if not |

---
## 9. Implementation Task List
(Ordered)
1. Inventory existing constants; add missing (`EXPLANATION`).
2. Update `EvaluationEventsEmitter`:
   - Event name constant.
   - Attribute mapping & removal of body usage for explanation.
3. Add unit tests for updated event format.
4. Introduce Splunk evaluation results emitter + factory wiring.
5. Add accumulation + single aggregated event emission.
6. Implement per-metric metric emission (dynamic creation or pre-registration strategy).
7. Add normalization utility + tests.
8. Add tests for aggregated event schema & metrics.
9. Optional: legacy compatibility flag + conditional emission path.
10. Documentation updates (this file + main README cross-link).

---
## 10. Risk & Mitigations
| Risk | Mitigation |
|------|------------|
| Breaking downstream queries | Provide legacy flag + clear changelog |
| High cardinality via evaluator names | Enforce sanitation & allow list if needed |
| Metric explosion (many evaluator names) | Recommend naming discipline; optionally gate dynamic creation |
| Performance overhead accumulating content | Reuse existing conversation capture toggle |

---
## 11. Example Diff Sketches (Illustrative Only)
```python
# evaluation.py (before)
_event_logger.emit(Event(name="gen_ai.evaluation", attributes=attrs, body=body))

# evaluation.py (after)
attrs["gen_ai.evaluation.explanation"] = res.explanation  # if present
_event_logger.emit(Event(name="gen_ai.evaluation.result", attributes=attrs))
```
```python
# splunk.py new emitter pseudo
class SplunkEvaluationResultsEmitter(EmitterMeta):
    role = "evaluation_results"
    def __init__(self, event_logger, meter, capture_content): ...
    def on_evaluation_results(self, results, obj=None): accumulate & emit metrics
    def on_end(self, obj): emit single aggregated event if any results
```

---
## 12. CHANGELOG (Planned)
Add to `CHANGELOG.md` (util-genai-dev):
```
### Unreleased
- BREAKING: Rename evaluation event from `gen_ai.evaluation` to `gen_ai.evaluation.result` (spec alignment).
- Added attribute `gen_ai.evaluation.explanation` (moved from event body).
- Added aggregated Splunk evaluation event (`gen_ai.splunk.evaluations`).
- Added per-evaluation metrics with naming pattern `gen_ai.evaluation.result.<metric_name>`.
- Added optional score normalization to [0,1].
- Added environment flag `OTEL_GENAI_EVALUATION_EVENT_LEGACY` to emit legacy event name (temporary).
```
Add to `CHANGELOG.md` (splunk emitter package):
```
### Unreleased
- Added aggregated evaluation + conversation event `gen_ai.splunk.evaluations`.
- Added per-evaluation metrics emission (one metric per evaluation result).
```

---
## 13. Success Criteria
- All new per-result events validate against semantic conventions attribute list.
- Tests cover: event attribute set, metric emission, normalization, aggregated event structure.
- No regression in existing conversation event emission.
- Optional legacy mode manually validated.

---
## 14. Next Steps After Merge
- Coordinate with backend ingestion team for parsing aggregated Splunk event.
- Provide example dashboard JSON for new metrics (follow-up PR).
- Evaluate adding evaluator latency instrumentation (future scope).

---
## 15. Appendix: Attribute Summary (New / Emphasized)
| Key | Layer | Notes |
|-----|-------|-------|
| gen_ai.evaluation.name | Event + Metrics attr | Metric identity (redundant when embedded in metric name) |
| gen_ai.evaluation.score.value | Event | Numeric score |
| gen_ai.evaluation.score.label | Event + Metric attr | Low cardinality bucket |
| gen_ai.evaluation.explanation | Event | Human-readable reasoning |
| gen_ai.response.id | Event | Correlate when span missing |
| gen_ai.evaluation.result.<metric_name> | Metric | One per evaluation type |

---
Prepared: (auto-generated draft)
