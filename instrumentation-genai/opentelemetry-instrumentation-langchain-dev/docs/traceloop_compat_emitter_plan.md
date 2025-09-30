# Traceloop Compatibility Emitter Implementation Plan

Status: Draft (Step 1 of user request)
Date: 2025-09-28
Owner: (to be filled by implementer)

## Goal
Add a pluggable GenAI telemetry "emitter" that recreates (as close as practical) the original Traceloop LangChain instrumentation span & attribute model while preserving the new `opentelemetry-util-genai-dev` architecture. Enable it via an environment variable so downstream users can opt into backward-compatible telemetry without forking.

## Summary
The current development callback handler (`opentelemetry-instrumentation-langchain-dev`) switched from in-place span construction (Traceloop style) to delegating LLM lifecycle to `TelemetryHandler` in `opentelemetry-util-genai-dev`. Some original Traceloop logic (hierarchical workflow / task / LLM spans and attribute conventions) is now commented out in:

`instrumentation-genai/opentelemetry-instrumentation-langchain-dev/src/opentelemetry/instrumentation/langchain/callback_handler.py`

Specifically inside:
- `on_chat_model_start` (original span creation commented)
- `on_llm_end` (original span finalization + usage attribution commented)

We will introduce a new emitter (e.g. `TraceloopCompatEmitter`) that can generate spans matching the *LLM span layer* semantics (naming + attributes) and optionally re-enable hierarchical spans for workflows/tasks if feasible with minimal callback modifications.

## Constraints & Design Principles
1. **Pluggable via env var** – Reuse `OTEL_INSTRUMENTATION_GENAI_EMITTERS`; add a new accepted token (proposal: `traceloop_compat`).
2. **Non-invasive** – Avoid large rewrites of `TelemetryHandler`; implement the emitter as an additional concrete emitter class living under `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/`.
3. **Graceful coexistence** – Allow combinations (e.g. `span_metric,traceloop_compat`) where Traceloop spans are produced alongside semconv spans (document implications / duplication risk).
4. **Backward-compatible naming** – Use span names & attributes patterned after original code (`<name>.<request_type>` for LLM spans, `workflow_name.task`, etc.).
5. **Trace shape** – If full hierarchy cannot be reproduced with only the current utility handler interface, provide at least equivalent LLM span attributes; optionally add a light modification to callback handler to emit workflow/task spans *only when env var is enabled*.
6. **Fail-safe** – If emitter misconfigured / errors, fallback silently to existing emitters (never break primary telemetry path).

## Current Architecture Overview (for Agent Reference)
Relevant directories/files:

| Purpose | Path |
|---------|------|
| Dev callback handler | `instrumentation-genai/opentelemetry-instrumentation-langchain-dev/src/opentelemetry/instrumentation/langchain/callback_handler.py` |
| Traceloop original reference | `traceloop/openllmetry/packages/opentelemetry-instrumentation-langchain/opentelemetry/instrumentation/langchain/callback_handler.py` |
| Util emitters package | `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/` |
| Existing emitters | `span.py`, `metrics.py`, `content_events.py`, `composite.py` |
| Telemetry handler | `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py` |
| Env vars constants | `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/environment_variables.py` |
| Env parsing | `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/config.py` |
| Types (LLMInvocation, messages) | `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/types.py` |
| Span attribute helpers (Traceloop) | `instrumentation-genai/.../span_utils.py` (already imported) |

## Extracted (Commented) Dev Handler Snippets
`on_chat_model_start` (current code uses util handler; original span creation commented):
```python
# name = self._get_name_from_callback(serialized, kwargs=kwargs)
# span = self._create_llm_span(
#     run_id,
#     parent_run_id,
#     name,
#     LLMRequestTypeValues.CHAT,
#     metadata=metadata,
#     serialized=serialized,
# )
# set_request_params(span, kwargs, self.spans[run_id])
# if should_emit_events():
#     self._emit_chat_input_events(messages)
# else:
#     set_chat_request(span, serialized, messages, kwargs, self.spans[run_id])
```

`on_llm_end` (commented original logic parallels active util-based logic):
```python
# generations = getattr(response, "generations", [])
# ... build content_text / finish_reason ...
# set_chat_response(span, response, self.spans[run_id])
# set_chat_response_usage(span, response, self.spans[run_id])
# self._end_span(span, run_id)
```

These indicate Traceloop originally:
- Created a CLIENT span with name `<callback_name>.chat` (request type appended)
- Attached request parameters and (optionally) captured prompts/messages either as attributes or emitted events
- On end: attached generation choices / usage tokens, determined model name from response metadata
- Recorded token metrics via `token_histogram`

## Traceloop Attribute Patterns (from original handler & helpers)
Custom attributes (names via `SpanAttributes` enum) include:
- `traceloop.workflow.name`
- `traceloop.entity.path`
- `traceloop.span.kind` (workflow | task | llm | tool)
- `traceloop.entity.name`
- `traceloop.entity.input` / `traceloop.entity.output` (JSON strings)
Plus semconv incubating GenAI attributes:
- `gen_ai.response.id`
- `gen_ai.request.model`
- `gen_ai.response.model` (when available)
- Token usage metrics (histograms) were recorded separately

## Proposed Additions
1. **New emitter class**: `traceloop_compat.py` implementing `start/finish/error/handles` similar to `SpanEmitter` but:
   - Span naming: `chat {request_model}` or `<name>.chat` (match original). Need to decide using invocation attributes; may pass `original_callback_name` in `LLMInvocation.attributes`.
   - Adds Traceloop-compatible attributes (entity/workflow names if provided).
   - Optionally supports hierarchical spans if caller supplies parent context (stretch goal – Phase 2).
2. **Environment Variable Extension**:
   - Extend `OTEL_INSTRUMENTATION_GENAI_EMITTERS` accepted values with `traceloop_compat`.
   - Parsing logic: if list contains `traceloop_compat`, append the new emitter to composed list (order after standard span emitter by default so traces include both styles or allow only traceloop when specified alone).
3. **Callback Handler Conditional Path**:
   - Add a lightweight feature flag check (e.g., inspect env once) to decide whether to:
     a. Keep current util-only flow (default), or
     b. Also populate Traceloop-specific runtime context (e.g., inject `original_callback_name` attribute into the `UtilLLMInvocation.attributes`).
   - Avoid reintroducing the full original span logic inside the handler; emitter should derive everything from enriched invocation.
4. **Invocation Attribute Enrichment**:
   - During `on_chat_model_start`, when traceloop compat flag is active:
     - Add keys:
       - `traceloop.entity.name` (the callback name)
       - `traceloop.workflow.name` (root chain name if determinable – may need small bookkeeping dictionary for run_id→workflow, replicating existing `self.spans` logic minimally or reuse `self.spans` holder already present).
       - `traceloop.span.kind` = `llm` for the LLM span (workflow/task spans Phase 2).
       - Raw inputs (if content capture enabled and events not used) aggregated into `traceloop.entity.input`.
   - On `on_llm_end` add similar output attributes (`traceloop.entity.output`) & usage if available.
5. **Metrics**: Continue using existing `MetricsEmitter`; no changes required (it already records duration + tokens).
6. **Content Capture**: Respect existing content capture mode env var; avoid duplicating message content on both traceloop and semconv spans simultaneously unless user explicitly chooses combined configuration.
7. **Documentation**: Add markdown doc (this file) plus update `environment_variables.py` docstring for new enum value and add a README blurb under `instrumentation-genai/opentelemetry-instrumentation-langchain-dev/docs/` (Phase 2).

## Implementation Phases
### Phase 1 (MVP – This Request Scope)
- [ ] Add new emitter class (LLM span only, no workflow/task hierarchy) producing Traceloop attribute keys & span naming.
- [ ] Add env var token handling (`traceloop_compat`).
- [ ] Inject minimal extra attributes in callback handler when flag active.
- [ ] Unit tests validating span name + key attributes presence.
- [ ] Update docs & changelog stub.

### Phase 2 (Optional / Future)
- Reintroduce workflow/task span hierarchy using a small state manager storing run_id relationships (mirroring old `self.spans` but only for naming + parent spans in compat mode).
- Emit tool call spans via either existing ToolCall start/stop or additional callback hooks.
- Add option to disable semconv span when traceloop compat is enabled alone (controlled by specifying ONLY `traceloop_compat` in env).

## Detailed Task Breakdown for Coding Agent
1. Parse Env Support
   - File: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/config.py`
     - Accept new token: if `gen_choice` contains `traceloop_compat` (comma-separated handling needed – currently single value). Adjust parsing to split list (today it treats as single). Option A: extend semantics so variable may be comma-separated; interpret first token as base flavor (span/span_metric/span_metric_event) and additional tokens as augmenting emitters.
     - Provide structured result: perhaps store an `extra_emitters: list[str]` field; **OR** (simpler) keep original fields and add a new function in handler to interrogate raw env string.
   - File: `environment_variables.py` – update docstring for `OTEL_INSTRUMENTATION_GENAI_EMITTERS` to mention `traceloop_compat`.
2. New Emitter
   - File: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/traceloop_compat.py`
     - Class `TraceloopCompatEmitter` with same interface (`start`, `finish`, `error`, `handles`).
     - On `start(LLMInvocation)`:
       - Determine span name: prefer `invocation.attributes.get("traceloop.callback_name")` else `f"{invocation.request_model}.chat"` or `f"chat {invocation.request_model}"` (decide consistent naming – original used `<name>.<request_type>`; supply `<callback_name>.chat`).
       - Start CLIENT span, set attributes:
         - `traceloop.span.kind = "llm"`
         - `traceloop.workflow.name` if present in attributes
         - `traceloop.entity.name` / `traceloop.entity.path`
         - Store raw inputs if `capture_content` and attribute key not suppressed.
         - Semconv attributes already added by `SpanEmitter`; to avoid duplication, optionally skip semconv span if configuration instructs (Phase 2). Initially we let both exist.
     - On `finish`: set outputs, usage (input/output tokens already on invocation), and `gen_ai.response.id` if available.
     - On `error`: set status and same final attributes.
   - Register export in `emitters/__init__.py` (optional if imported directly by handler).
3. TelemetryHandler Wiring
   - File: `handler.py`
     - After constructing base emitters list, check env raw string or `settings` for presence of `traceloop_compat`.
     - If present, import and append `TraceloopCompatEmitter` instance (respect appropriate capture flags – may use span-only content capturing mode or its own internal flag mirroring `SpanEmitter`).
4. Callback Handler Adjustments
   - File: `instrumentation-genai/.../callback_handler.py`
     - Introduce a module-level lazy boolean `_TRACELOOP_COMPAT_ENABLED` evaluating env once (`os.getenv("OTEL_INSTRUMENTATION_GENAI_EMITTERS", "").lower()` contains `traceloop_compat`).
     - In `on_chat_model_start` before creating `UtilLLMInvocation`, compute `callback_name = self._get_name_from_callback(serialized, kwargs=kwargs)` and if compat enabled add:
       ```python
       attrs["traceloop.callback_name"] = callback_name
       attrs["traceloop.span.kind"] = "llm"
       # For Phase 2, optionally add workflow/entity placeholders
       ```
     - In `on_llm_end` after tokens & content resolution, if compat enabled add:
       ```python
       if inv.output_messages:
           inv.attributes["traceloop.entity.output"] = json.dumps([m.__dict__ for m in inv.output_messages])
       if inv.input_messages:
           inv.attributes.setdefault("traceloop.entity.input", json.dumps([m.__dict__ for m in inv.input_messages]))
       if inv.response_id:
           inv.attributes["gen_ai.response.id"] = inv.response_id
       ```
     - (DON'T resurrect old span logic here; emitter will consume these attributes.)
5. Tests
   - Location: `util/opentelemetry-util-genai-dev/tests/` (create new test file `test_traceloop_compat_emitter.py`).
   - Cases:
     1. Enabling env var yields additional span with expected name `<callback_name>.chat` and attributes present.
     2. Without env var, no traceloop attributes appear on emitted semconv span.
     3. Token usage still recorded exactly once (metrics unaffected).
     4. Error path sets error status.
   - Use in-memory span exporter to capture spans and assert counts & attribute keys.
6. Documentation Updates
   - This plan file committed.
   - Add bullet to `langchain_instrumentation_gap_analysis.md` referencing traceloop compat emitter availability.
   - Extend env var docs in `environment_variables.py`.
7. Changelog Stub
   - Add entry in root or instrumentation package CHANGELOG (depending on repo practice) noting new `traceloop_compat` emitter.

## Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Duplicate spans increase cost | Document clearly; allow users to specify ONLY `traceloop_compat` to suppress standard span emitter in Phase 2. |
| Attribute name collisions | Prefix all custom keys with `traceloop.` (as original). |
| Performance overhead | Lightweight; optional path only when env var present. |
| Future removal of Traceloop custom attributes | Isolated in one emitter; easy deprecation path. |

## Open Questions (Flag for Maintainers)
1. Should `traceloop_compat` suppress the default semconv span automatically when used alone? (Recommend: yes – document expectation.)
2. Do we need hierarchical workflow/task spans for MVP? (Recommend: defer; collect feedback.)
3. Should we map `traceloop.span.kind` to semconv `gen_ai.operation.name` or keep separate? (Keep separate for purity.)

## Acceptance Criteria (Phase 1)
- Env var `OTEL_INSTRUMENTATION_GENAI_EMITTERS=traceloop_compat` produces one span per LLM invocation named `<callback_name>.chat` with Traceloop attribute keys.
- Combined config `OTEL_INSTRUMENTATION_GENAI_EMITTERS=span_metric,traceloop_compat` produces both semconv span + traceloop compat span.
- No uncaught exceptions when flag enabled/disabled.
- Existing tests pass; new tests validate emitter behavior.

## Example Environment Configurations
| Desired Output | Env Setting |
|----------------|------------|
| Standard spans only (current default) | (unset) or `span` |
| Standard spans + metrics | `span_metric` |
| Standard spans + metrics + content events | `span_metric_event` |
| Traceloop compat only | `traceloop_compat` |
| Standard span + traceloop compat | `span,traceloop_compat` |
| Standard full (span+metric+events) + traceloop | `span_metric_event,traceloop_compat` |

(Note: Parsing update must allow comma-separated tokens.)

## Pseudocode Illustrations
### Emitter Skeleton
```python
class TraceloopCompatEmitter:
    role = "traceloop_compat"
    name = "traceloop_compat_span"

    def __init__(self, tracer=None, capture_content=False):
        self._tracer = tracer or trace.get_tracer(__name__)
        self._capture_content = capture_content

    def handles(self, obj):
        return isinstance(obj, LLMInvocation)

    def start(self, invocation: LLMInvocation):
        cb_name = invocation.attributes.get("traceloop.callback_name") or invocation.request_model or "unknown"
        span_name = f"{cb_name}.chat"
        cm = self._tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT, end_on_exit=False)
        span = cm.__enter__()
        invocation.attributes.setdefault("traceloop.span.kind", "llm")
        for k, v in invocation.attributes.items():
            if k.startswith("traceloop."):
                span.set_attribute(k, v)
        if self._capture_content and invocation.input_messages:
            span.set_attribute("traceloop.entity.input", json.dumps([asdict(m) for m in invocation.input_messages]))
        invocation.__dict__["traceloop_span"] = span
        invocation.__dict__["traceloop_cm"] = cm

    def finish(self, invocation: LLMInvocation):
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if not span:
            return
        if self._capture_content and invocation.output_messages:
            span.set_attribute("traceloop.entity.output", json.dumps([asdict(m) for m in invocation.output_messages]))
        if invocation.response_id:
            span.set_attribute(GEN_AI_RESPONSE_ID, invocation.response_id)
        if cm and hasattr(cm, "__exit__"):
            cm.__exit__(None, None, None)
        span.end()

    def error(self, error: Error, invocation: LLMInvocation):
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if not span:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if cm and hasattr(cm, "__exit__"):
            cm.__exit__(None, None, None)
        span.end()
```

### Handler Integration (Snippet)
```python
raw = os.getenv(OTEL_INSTRUMENTATION_GENAI_EMITTERS, "span")
tokens = [t.strip().lower() for t in raw.split(',') if t.strip()]
base = next((t for t in tokens if t in {"span", "span_metric", "span_metric_event"}), "span")
extra = [t for t in tokens if t not in {base}]
# existing logic picks base -> emitters list
if "traceloop_compat" in extra:
    from .emitters.traceloop_compat import TraceloopCompatEmitter
    emitters.append(TraceloopCompatEmitter(tracer=self._tracer, capture_content=capture_span or capture_events))
```

### Callback Attribute Enrichment
```python
if _TRACELOOP_COMPAT_ENABLED:
    callback_name = self._get_name_from_callback(serialized, kwargs=kwargs)
    attrs["traceloop.callback_name"] = callback_name
    attrs.setdefault("traceloop.span.kind", "llm")
```

## Test Assertion Examples
```python
# After running a simple Chat model invocation with traceloop_compat only:
spans = exporter.get_finished_spans()
assert any(s.name.endswith('.chat') and 'traceloop.span.kind' in s.attributes for s in spans)
```

## Rollback Strategy
All changes are additive behind an env flag; rollback is simply removing the emitter file and references. No persistent schema migration or public API change.

## Next Step
Implement Phase 1 tasks exactly as listed. This document serves as the execution checklist for the coding AI agent.

---
End of Plan.

