# LangChain Instrumentation Gap Analysis & Implementation Plan

## 1. Purpose
This document analyzes differences between the Traceloop `opentelemetry-instrumentation-langchain` implementation ("Traceloop version") and the current upstream development package `opentelemetry-instrumentation-langchain-dev` ("Dev version"), and proposes a phased plan to close functionality gaps by leveraging / extending `opentelemetry-util-genai-dev`.

It also answers: Should we copy the entire Traceloop package first, or incrementally evolve the Dev version? And: What new concepts must be added to `opentelemetry-util-genai-dev` to support feature parity cleanly?

---
## 2. High-Level Summary
The Traceloop version implements a rich, hierarchical span model (workflow → task → LLM/tool), prompt/response capture (attributes or events), tool call recording, token & duration metrics, vendor/model detection heuristics, and robust error context management. The Dev version currently creates *only one* LLM invocation span per `on_chat_model_start` → `on_llm_end/error` lifecycle and relies on `opentelemetry-util-genai-dev` for span + metrics emission.

`opentelemetry-util-genai-dev` already supports:
- Generic lifecycle management for LLM/Embedding/ToolCall invocations
- Unified span + metrics + optional content event generation
- Evaluation (length/sentiment, optional DeepEval) post-completion

It does **not yet** offer explicit primitives for: workflows / chains / tasks, entity path composition, structured function/tool definition attributes (semconv-aligned), per-generation multi-choice output modeling, hierarchical run_id propagation semantics beyond existing `parent_run_id` storage, or streaming chunk events.

---
## 3. Feature Matrix (Gap Overview)
| Feature | Traceloop Version | Dev Version | util-genai-dev Support | Gap Action |
|---------|-------------------|-------------|------------------------|------------|
| Workflow span (root chain) | Yes (`WORKFLOW`) | No | No (needs type) | Add `WorkflowInvocation` or reuse Task with type=workflow |
| Task span (nested chains/tools) | Yes (`TASK`) | No | No | Add `TaskInvocation` with parent linkage |
| Tool span & lifecycle | Yes (start/end/error) | No-op methods | Partial (`ToolCall` dataclass & lifecycle in handler) | Wire callbacks to util handler start/stop/fail |
| LLM span request params | Temperature, top_p, max tokens, function definitions, model names | Partial (some params via attributes) | Partial (generic attributes) | Add structured semconv / naming alignment |
| Prompt capture (messages) | Yes (span attrs OR events gated by env) | Basic (input messages) | Yes (content span or events) | Extend to multi-choice & tool call metadata |
| Response capture (multiple choices) | Yes (completions indexed) | Only first generation captured | Partial (output_messages list) | Populate all generations as OutputMessages |
| Tool/function definitions | Span attributes (indexed) | Partial (custom keys) | Not semantic-coded | Normalize attribute keys to spec-like scheme |
| Tool calls in prompts & responses | Yes (both prompt tool calls & response tool calls) | No | Has `ToolCall` dataclass, but not wired | Parse & attach to Input/OutputMessage parts |
| Token usage (direct + aggregated from message usage_metadata) | Yes (2 paths) | Only aggregated from llm_output.usage | Partial (invocation.input_tokens/output_tokens) | Add fallback aggregator from per-message usage_metadata |
| Cache read token metrics | Yes | No | Not yet | Add attribute & metric field (e.g. `gen_ai.usage.cache_read_input_tokens`) |
| Duration metric | Yes (histogram) | Yes (via MetricsEmitter) | Yes | Ensure tasks/tools also recorded |
| Vendor detection | Heuristic (`detect_vendor_from_class`) | No | No (simple provider passthrough) | Add heuristic util (model/provider inference) |
| Safe context attach/detach | Custom defensive logic | Implicit via context manager | Provided by tracer context managers | Accept simpler unless edge cases observed |
| Error classification (error.type attr) | Yes (`error.type`) | Yes (type in Error object) | Sets span status | Add explicit `error.type` attribute (already partially) |
| Association metadata propagation | Yes (context key `association_properties`) | No | No | Decide if needed; could map to attributes instead |
| Event emission mode (MessageEvent / ChoiceEvent) | Yes (alternate to span attributes) | Not per-message | ContentEventsEmitter dumps full invocation | Optional Phase: implement per-message event emitter |
| Streaming / chunk handling | ChoiceEvent supports `ChatGenerationChunk` | Not implemented | Not implemented | Future: callback hooks (`on_llm_new_token`) to incremental events |
| Finish reasons | Extracted per generation | First only | OutputMessage has finish_reason | Populate for each generation |
| Structured hierarchical entity path | Yes (entity_path, workflow_name) | No | No | Add attributes (`gen_ai.workflow.name`, `gen_ai.entity.path`, `gen_ai.entity.name`) |

---
## 4. Copy vs Incremental Approach
### Option A: Copy Entire Traceloop Implementation
Pros:
- Fast initial parity
- Battle-tested logic (edge cases: context detach, tool call parsing)
- Lower short-term engineering cost
Cons:
- Brings Traceloop-specific attribute names (`traceloop.*`, `SpanAttributes.TRACELOOP_*`) not aligned with upstream semantics
- Duplicates functionality that util-genai is intended to centralize
- Harder refactor later (semantic drift, technical debt)
- Increased maintenance surface (two parallel paradigms)

### Option B: Incrementally Extend Dev Version (Recommended)
Pros:
- Keeps `opentelemetry-util-genai-dev` as single source of truth for lifecycle logic
- Enforces semantic consistency with incubating OpenTelemetry GenAI attributes
- Cleaner evolution path toward standardization
- Smaller, reviewable PRs (phased delivery)
Cons:
- More up-front design work for new abstractions (workflow/task)
- Need to re-implement some edge case logic (tool call extraction, fallback model detection)

### Option C: Hybrid (Temporary Fork + Guided Migration)
- Copy selective helper functions (tool call extraction, token aggregation) but not entire class
- Adopt util-genai early in all new code

Recommendation: Option B (Incremental) with selective borrowing of parsing helpers from Traceloop.

---
## 5. Proposed Phased Plan
| Phase | Goal | Scope | Exit Criteria |
|-------|------|-------|---------------|
| 0 | Foundations & attribute alignment | Add new attribute constants & vendor heuristic | Attributes compile; no behavior regression |
| 1 | Task & Workflow spans | Add `TaskInvocation` (also used for workflow) & handler APIs | Spans appear with correct parentage & metrics |
| 2 | Tool call lifecycle | Wire LangChain tool callbacks to `ToolCall` start/stop/fail | Tool spans & metrics emitted |
| 3 | Multi-choice output + finish reasons | Populate all generations; aggregate usage tokens fallback | All choices visible; token metrics stable |
| 4 | Prompt & response tool call metadata | Parse tool calls in prompts and assistant outputs | Tool call parts present in messages |
| 5 | Event emission parity | Optional per-message emitter (Message/Choice style) | Env toggle selects span attrs vs events |
| 6 | Streaming & chunk support | Implement `on_llm_new_token` → incremental events | Tokens appear in near-real time (if enabled) |
| 7 | Advanced metadata (association) | Decide minimal upstream mapping (maybe defer) | Decision recorded & implemented or deferred |
| 8 | Evaluations integration consistency | Ensure evaluation spans/events/metrics align with new model | Evaluations run seamlessly with tasks |

---
## 6. Required Additions to `opentelemetry-util-genai-dev`
### 6.1 New Types
```python
@dataclass
class TaskInvocation:
    name: str
    kind: Literal["workflow", "task"]
    workflow_name: str  # workflow root name (== name if kind==workflow)
    entity_path: str    # dotted path of ancestors (excluding self)
    run_id: UUID = field(default_factory=uuid4)
    parent_run_id: Optional[UUID] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    span: Optional[Span] = None
    context_token: Optional[ContextToken] = None
    attributes: dict[str, Any] = field(default_factory=dict)
```
(Alternatively: Generalize with a protocol; explicit dataclass clearer.)

### 6.2 Attribute Constants
Add to `attributes.py`:
- `GEN_AI_WORKFLOW_NAME = "gen_ai.workflow.name"`
- `GEN_AI_ENTITY_NAME = "gen_ai.entity.name"`
- `GEN_AI_ENTITY_PATH = "gen_ai.entity.path"`
- Optionally `GEN_AI_SPAN_KIND = "gen_ai.span.kind"` (values: workflow | task | tool_call | chat | embedding)
- (Optional) `GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read_input_tokens"`

### 6.3 TelemetryHandler Extensions
```python
def start_task(self, inv: TaskInvocation): self._generator.start(inv)
def stop_task(self, inv: TaskInvocation): inv.end_time=time.time(); self._generator.finish(inv)
def fail_task(self, inv: TaskInvocation, error: Error): inv.end_time=time.time(); self._generator.error(error, inv)
```

### 6.4 SpanEmitter Updates
- Recognize `TaskInvocation`
- Span name rules:
  - workflow: `workflow {workflow_name}`
  - task: `task {name}` (or include path for disambiguation)
- Attributes set:
  - `GEN_AI_WORKFLOW_NAME`
  - `GEN_AI_ENTITY_NAME`
  - `GEN_AI_ENTITY_PATH` (empty for root)
  - `GEN_AI_SPAN_KIND`
- Keep `SpanKind.INTERNAL` for workflow/task; keep `CLIENT` for LLM/tool/embedding.

### 6.5 MetricsEmitter Updates
- Accept `TaskInvocation` and record duration histogram (same histogram as LLM for simplicity).

### 6.6 ToolCall Integration Enhancements
- (Optional) Consider splitting tool call metrics vs llm metrics by adding `operation` attribute values (`tool_call`). Already partially handled.
- Add parsing helper to LangChain handler to create `ToolCall` objects with arguments, name, id from message/tool data.

### 6.7 Multi-Choice Output Support
- Permit `LLMInvocation.output_messages` to contain >1 assistant response (each with `finish_reason`). Already structurally supported—only LangChain adapter must populate.
- Optionally add a convenience helper in util-genai: `normalize_generations(response: LLMResult) -> list[OutputMessage]`.

### 6.8 Token Usage Aggregation Helper
Add util function:
```python
def aggregate_usage_from_generations(response: LLMResult) -> tuple[int,int,int,int]:
    # returns input_tokens, output_tokens, total_tokens, cache_read_tokens
```
Used if invocation.input_tokens/output_tokens unset and per-message usage available.

### 6.9 Optional Event Emitter for Per-Message Events
- New emitter `PerMessageEventsEmitter` producing two event types:
  - `gen_ai.message` (role, index, content, tool_calls)
  - `gen_ai.choice` (index, finish_reason, tool_calls)
- Controlled by env var (e.g. `OTEL_INSTRUMENTATION_GENAI_EVENT_MODE=aggregate|per_message`).
- Phase 5 (optional) — can be deferred until after parity of spans/metrics.

### 6.10 Vendor / Provider Heuristic
Add helper:
```python
def infer_provider(model: str | None) -> str | None:
    if not model: return None
    m = model.lower()
    if any(x in m for x in ("gpt", "o3", "o1")): return "openai"
    if "claude" in m: return "anthropic"
    if m.startswith("gdrive" ) ... # extend
    return None
```
Fallback order in LangChain handler:
1. metadata.ls_provider
2. invocation_params.model_name pattern inference
3. None

### 6.11 Error Attribute Harmonization
Ensure `SpanEmitter.error` sets `error.type` (already sets `error.type` via semconv). Optionally add `gen_ai.error.type` alias if needed for analytics.

---
## 7. Changes to LangChain Dev Callback Handler
### 7.1 Data Structures
Maintain three dicts or unified map keyed by `run_id`:
- `tasks: dict[UUID, TaskInvocation]`
- `llms: dict[UUID, LLMInvocation]`
- `tools: dict[UUID, ToolCall]`
(Or one `invocations` dict mapping run_id → object; type-checked at use.)

### 7.2 Chain / Workflow Lifecycle
Implement:
```python
on_chain_start(serialized, inputs, run_id, parent_run_id, metadata, **kwargs):
    name = _derive_name(serialized, kwargs)
    if parent_run_id is None: kind="workflow"; workflow_name=name; entity_path=""
    else: kind="task"; workflow_name = tasks[parent].workflow_name; entity_path = compute_entity_path(parent)
    inv = TaskInvocation(name=name, kind=kind, workflow_name=workflow_name, entity_path=entity_path, parent_run_id=parent_run_id, attributes={"framework":"langchain"})
    telemetry.start_task(inv)
    tasks[run_id] = inv
```
On end/error: call `stop_task` or `fail_task` then remove from dict.

### 7.3 Tool Lifecycle
Use existing callbacks; parse raw inputs (serialized, input_str/inputs) into `ToolCall` with:
- `name` from serialized / kwargs
- `arguments` JSON (original input)
- `attributes` include framework, maybe function index if definable
Call `telemetry.start_tool_call` / `stop_tool_call` / `fail_tool_call`.

### 7.4 LLM Start
Current logic mostly retained; now also set `parent_run_id`; propagate provider inference; attach function definition attributes.

### 7.5 LLM End
Populate:
- All generations as output messages (loop over `response.generations`)
- Each finish_reason
- Tool calls (function_call or tool_calls arrays) as additional parts appended after text part (order preserved)
- Usage aggregation fallback if `llm_output.usage` absent
- Cache read tokens if available in `usage_metadata.input_token_details.cache_read`
Then call `stop_llm`.

### 7.6 LLM Error
Forward to `fail_llm`.

### 7.7 Helper Functions to Borrow / Adapt from Traceloop
- `_extract_tool_call_data` (adapt to produce ToolCall message parts, not spans)
- Token aggregation loop (from `set_chat_response_usage`)
- Name derivation heuristic (`_get_name_from_callback`)

### 7.8 Attribute Alignment
Map:
| Traceloop | Dev / util-genai target |
|-----------|-------------------------|
| `SpanAttributes.LLM_REQUEST_FUNCTIONS.{i}.name` | `gen_ai.request.function.{i}.name` |
| `...description` | `gen_ai.request.function.{i}.description` |
| `...parameters` | `gen_ai.request.function.{i}.parameters` |
| Prompts/Completions indexing | (Content captured in messages JSON; optional per-message events) |
| TRACELOOP_WORKFLOW_NAME | `gen_ai.workflow.name` |
| TRACELOOP_ENTITY_PATH | `gen_ai.entity.path` |
| TRACELOOP_ENTITY_NAME | `gen_ai.entity.name` |
| LLM_USAGE_* | `gen_ai.usage.*` (already partly supported) |

### 7.9 Streaming Tokens (Phase 6)
Implement `on_llm_new_token(token, run_id, **kwargs)`:
- If per-message events mode enabled, emit incremental `gen_ai.delta` event.
- Optionally accumulate partial text; final assembly done on `on_llm_end`.

---
## 8. Backwards Compatibility Considerations
- Existing Dev users: still get single LLM span; after Phase 1 they also see workflow/task spans. Provide environment toggle to disable workflow/task if necessary (`OTEL_INSTRUMENTATION_LANGCHAIN_TASK_SPANS=0`).
- Attribute naming stability: Introduce new attributes without removing existing until deprecation notice.
- Avoid breaking tests: Expand tests gradually; keep initial expectations by adding new assertions rather than replacing.

---
## 9. Testing Strategy
| Area | Tests |
|------|-------|
| Workflow/task spans | Start nested chains; assert parent-child IDs and attributes |
| Tool calls | Simulated tool invocation with arguments; assert span & duration metric |
| Function definitions | Provide two functions; assert indexed attributes exist |
| Multi-choice responses | Mock multiple generations; assert multiple OutputMessages |
| Token aggregation fallback | Response with per-message usage only; assert metrics recorded |
| Cache read tokens | Provide usage_metadata; assert `gen_ai.usage.cache_read_input_tokens` |
| Error flows | Force exception in tool & llm; assert error status & type |
| Provider inference | Provide model names; verify provider attribute |
| Event emission modes | Toggle each mode; assert presence/absence of content attributes vs events |

---
## 10. Risk & Mitigation
| Risk | Mitigation |
|------|------------|
| Attribute name churn (spec evolution) | Centralize in `attributes.py`; one change point |
| Performance (extra spans) | Configurable toggles; measure overhead with benchmarks |
| Duplicate token counting | Guard aggregation only if invocation tokens unset |
| Streaming complexity | Isolate in later phase; keep initial design simple |
| Tool call misclassification | Defensive parsing & unit tests with diverse structures |

---
## 11. Work Breakdown (File-Level)
| File | Change Summary |
|------|----------------|
| util-genai-dev `types.py` | Add `TaskInvocation` dataclass |
| util-genai-dev `attributes.py` | New constants (workflow/entity/path/cache tokens) |
| util-genai-dev `handler.py` | Add start/stop/fail task functions; export in `__all__` |
| util-genai-dev `emitters/span.py` | Recognize TaskInvocation, set attributes, SpanKind.INTERNAL |
| util-genai-dev `emitters/metrics.py` | Record duration for TaskInvocation |
| util-genai-dev `utils.py` | Add provider inference & usage aggregation helper |
| langchain-dev `callback_handler.py` | Implement chain/task/tool lifecycle + multi-choice output |
| langchain-dev tests | Add new test modules: test_tasks.py, test_tool_calls.py, test_multi_generation.py |
| docs (this file) | Keep updated per phase |

---
## 12. Pseudo-Code Snippets
### Task Invocation Start (LangChain handler)
```python
from opentelemetry.util.genai.types import TaskInvocation

if parent_run_id is None:
    kind = "workflow"; workflow_name = name; entity_path = ""
else:
    parent = _invocations[parent_run_id]
    workflow_name = parent.workflow_name
    entity_path = f"{parent.entity_path}.{parent.name}" if parent.entity_path else parent.name
    kind = "task"
inv = TaskInvocation(name=name, kind=kind, workflow_name=workflow_name, entity_path=entity_path, parent_run_id=parent_run_id, attributes={"framework":"langchain"})
telemetry.start_task(inv)
_invocations[run_id] = inv
```

### Multi-Choice Generation Mapping
```python
outs = []
for choice_idx, gen in enumerate(response.generations[0]):
    text = getattr(gen, "text", None) or getattr(gen.message, "content", "")
    finish = (getattr(gen, "generation_info", {}) or {}).get("finish_reason", "stop")
    parts = [UtilText(content=str(text))]
    # append tool calls if present
    outs.append(UtilOutputMessage(role="assistant", parts=parts, finish_reason=finish))
inv.output_messages = outs
```

### Token Aggregation Fallback
```python
if inv.input_tokens is None and inv.output_tokens is None:
    in_tok, out_tok, total, cache_read = aggregate_usage_from_generations(response)
    if in_tok or out_tok:
        inv.input_tokens = in_tok
        inv.output_tokens = out_tok
        inv.attributes["gen_ai.usage.total_tokens"] = total
        if cache_read: inv.attributes["gen_ai.usage.cache_read_input_tokens"] = cache_read
```

---
## 13. Decision Points (Need Confirmation or Future Spec Alignment)
| Topic | Question | Interim Answer |
|-------|----------|----------------|
| Attribute naming for function defs | Use `gen_ai.request.function.N.*`? | Yes (consistent with current dev style) |
| Expose workflow/task spans by default | Opt-out or opt-in? | Default ON with env to disable |
| Association metadata | Promote to attributes? | Defer until real user need appears |
| Per-message events | Necessary for MVP parity? | Optional Phase 5 |
| Streaming tokens | Needed early? | Defer to Phase 6 |

---
## 14. Recommended Next Actions (Immediate)
1. Implement util-genai additions: attributes + TaskInvocation + handler + emitters.
2. Extend LangChain dev handler with workflow/task/tool lifecycle; keep existing LLM logic.
3. Add multi-choice + usage aggregation; adjust tests.
4. Release as experimental; gather feedback before adding events/streaming.

---
## 15. Summary
Incremental enhancement using `opentelemetry-util-genai-dev` as the central lifecycle engine yields a cleaner, spec-aligned design with manageable complexity. Copying the full Traceloop code would increase short-term speed but introduce long-term maintenance friction. A phased approach ensures stable progress while minimizing risk.

(End of document)

