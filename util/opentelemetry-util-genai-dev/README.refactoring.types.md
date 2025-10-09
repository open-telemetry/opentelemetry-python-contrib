# GenAI Types Refactor Plan for LangChain Instrumentation

Status: DRAFT (initial plan)  
Owner: (add GitHub handle)  
Last Updated: 2025-10-08

## 1. Objective
Refactor `opentelemetry-instrumentation-langchain-dev` so it no longer emits spans / attributes directly. Instead it constructs GenAI dataclass instances (`LLMInvocation`, `Workflow`, `AgentInvocation`, `Task`, `ToolCall`) and drives emission exclusively through `opentelemetry.util.genai` (`TelemetryHandler`). This aligns LangChain instrumentation with the implementation‑aligned architecture and enables: centralized emitter configuration, evaluation pipeline reuse, consistent semantic conventions, and simplified vendor flavor extensions.

### Vendor-Neutral Schema Rule
GenAI dataclasses MUST remain vendor-neutral:
- Do not introduce proprietary or emitter-specific prefixes (e.g. `traceloop.*`) into field names or directly into `attributes` at instrumentation time.
- Fields representing approved semantic convention attributes are annotated via `metadata={"semconv": <spec key>}`.
- Pre-spec / provisional concepts use neutral descriptive names (e.g. `framework`, `tools`, `input_context`).
- Legacy LangChain / provider metadata gathered during callbacks is stored under a single neutral container key: `attributes['langchain_legacy']` (dictionary) — never `_ls_metadata`, never flattened vendor keys.
- Vendor emitters (e.g. a Traceloop emitter) are solely responsible for mapping neutral dataclass fields + `langchain_legacy` contents into proprietary attribute namespaces.

Instrumentation MUST NOT set keys beginning with `traceloop.` or raw `ls_*` directly on spans; such projection logic lives only in emitters.

## 2. Current State (Summary)
The callback handler mixes two patterns:
- Direct OpenTelemetry span creation + attribute setting (legacy Traceloop style)
- Partial adoption of util‑genai (`LLMInvocation` + `AgentInvocation` objects for chat model start/end)
It still:
- Creates spans for chains/tools/LLM completions manually.
- Filters / normalizes params ad hoc (ls_* keys) inside handler.
- Emits request/response prompt data through span attributes or events depending on env gating.

### Recent Progress Snapshot
- Replaced internal span maps with `_entities`/`_llms` registries and routed lifecycle calls through `TelemetryHandler`.
- Chain, tool, agent, and LLM callbacks now build neutral GenAI dataclasses and preserve `langchain_legacy` metadata.
- Metrics emitters attach span context when recording so exemplars are emitted (still validating via tests).

### Outstanding Issues
- `tests/test_langchain_llm.py::test_langchain_call` currently fails because token usage exemplars are missing in replayed metrics. Investigate histogram context propagation.
- `tests/test_langchain_llm.py::test_langchain_call_with_tools` produces no spans under VCR replay with the new entity pipeline; trace suppression or parent linkage needs debugging.
- Pytest runs inside the sandbox require disabling the rerunfailures plugin; outside-sandbox verification still pending.

## 3. Target Model
LangChain callbacks map to GenAI invocation types:
| LangChain Callback | GenAI Type | Notes / Parent Link |
|--------------------|-----------|---------------------|
| `on_chat_model_start` | `LLMInvocation` | `parent_run_id` links to enclosing `AgentInvocation` or `Workflow` if present. |
| `on_llm_start` | (Initial Phase) `LLMInvocation` | Non-chat, treat as completion style; same dataclass. |
| `on_llm_end` | (Finish) same `LLMInvocation` | Populate response fields, tokens, finish reasons then `stop_llm()`. |
| `on_chain_start` (root) | `Workflow` | First chain in a trace becomes a `Workflow`. |
| `on_chain_start` (nested non-agent) | `Task` | Nested chain that is not agent -> `Task` child of workflow / agent. |
| `on_chain_start` (agent detected) | `AgentInvocation` | Use heuristics already present to classify. |
| `on_chain_end` | Finish corresponding object | `stop_workflow` / `stop_task` / `stop_agent`. |
| `on_tool_start` | `Task` (or future `ToolInvocation`) | Represent tool execution as `Task` with `task_type="tool_use"` and name=tool. (Optional future: distinct `ToolInvocation` dataclass). |
| `on_tool_end` | Finish Task | Set `output_data`. |
| `on_*_error` | Fail relevant type | Use `fail_*` API with `Error(message, type)` before discarding state. |

## 4. Required / Proposed Type Adjustments
| Type | Change | Rationale |
|------|--------|-----------|
| `Workflow` | Add semconv fields? (None needed now) | Keep minimal; semantic conventions for workflows evolving. |
| `AgentInvocation` | Already includes `operation`, `description`, `model`, `tools` | Ensure mapping of agent id/name from run_id and name. |
| `Task` | Reuse for chain/task/tool nodes | Avoid over-proliferation; `task_type` differentiates (chain, tool, internal). |
| `ToolCall` | Already present for LLM tool calls (function calling) | No change; enumeration occurs inside LLM content parts. |
| New (defer) | `ToolInvocation` specialized dataclass | Only if semantics diverge strongly from generic Task. |

No immediate schema changes required; rely on `attributes` for ancillary *neutral* data (tags, metadata). Add helper to convert LangChain metadata into sanitized `attributes` while placing any legacy `ls_*` / LangChain-specific keys inside `attributes['langchain_legacy']` (a dict). Vendor emitters may later translate those into their own prefixed attributes.

## 5. Event → GenAI Lifecycle Mapping
```
chat start  -> build LLMInvocation -> handler.start_llm
chat end    -> populate response_* tokens -> handler.stop_llm
chain start (root, non-agent) -> build Workflow -> handler.start_workflow
chain start (agent) -> build AgentInvocation -> handler.start_agent
chain start (nested non-agent) -> build Task(task_type="chain") -> handler.start_task
tool start  -> build Task(task_type="tool_use") -> handler.start_task
chain/tool end -> set outputs -> handler.stop_*(obj)
errors (llm/chain/tool/agent) -> handler.fail_*(obj, Error)
```
Parent propagation: Keep dict[run_id -> GenAI] similar to existing `_invocations` / `_agents`; unify under `_entities` with a typed wrapper so we can look up parent quickly and populate `parent_run_id`.

## 6. State Management Strategy
Internal maps:
- `_entities: dict[UUID, GenAI]` stores all active objects (workflow, agent, task, llm).
- `_llms: dict[UUID, LLMInvocation]` subset for quick access.
- Optional stacks are derivable via parent links; no explicit stack structure required.
Creation rules:
1. Root `on_chain_start` with no parent -> Workflow.
2. `on_chain_start` with agent heuristic true -> AgentInvocation.
3. Other chain start -> Task(task_type="chain").
4. `on_tool_start` -> Task(task_type="tool_use").
5. LLM chat/completion -> LLMInvocation (child of enclosing agent/task/workflow). If parent is AgentInvocation, copy `agent_name/id`.

## 7. Error Handling
- On `on_*_error`, locate entity, populate any partial fields (e.g., `output_result=str(error)` for Agent, `output_data` for Task) then call `fail_*` with `UtilError(message, type(exception))`.
- Ensure entity removal from `_entities` after fail to avoid memory growth.

## 8. Token & Content Population
LLM end:
- Extract first generation content + finish_reason.
- Map usage: `prompt_tokens -> input_tokens`, `completion_tokens -> output_tokens`.
- Functions/tool calls: push into `request_functions` if available at start; response tool calls appear as output message parts if LangChain provides them (future – currently minimal).
Tasks / tools:
- Serialize inputs/outputs into `input_data` / `output_data` when JSON-serializable and small (< configurable size threshold, e.g., 8 KB) else put a truncated marker and length attribute.

## 9. Telemetry Handler Integration Pattern
Provide helper methods:
```python
def _start(entity: GenAI) -> None: ...  # dispatches to handler based on isinstance

def _stop(entity: GenAI) -> None: ...

def _fail(entity: GenAI, exc: BaseException) -> None: ...
```
This removes duplication in callback methods.

## 10. Refactoring Steps / Tasks
(Each should become a PR / changelog entry.)
1. Introduce `_entities` registry + helpers without changing current behavior (internal prep).
2. Replace direct span creation for chat model start/end with existing util calls (already partially done) — remove legacy commented span code.
3. Implement Workflow/Agent/Task creation logic in `on_chain_start` / `on_tool_start`; adjust `on_chain_end`, `on_tool_end` to stop entities instead of ending spans.
4. Migrate error pathways to `_fail` helper invoking handler.fail_*.
5. Remove now-unused span creation utilities for LLM spans (`_create_llm_span`, `set_llm_request`, etc.) or gate behind legacy flag for rollback (since dev branch, removal acceptable).
6. Purge residual attribute setting / association_properties logic (rely on util emitters for semantic attr projection). Retain minimal metadata sanitation to fill `attributes` dict of dataclasses.
7. Add task/tool output serialization & truncation helper.
8. Update tests & examples to validate new pipeline (spans still produced through util emitters, but instrumentation no longer sets them directly).
9. Update docs: this README (plan) and `README.refactoring.telemetry.md` changelog.

## 11. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Loss of vendor-specific attributes (ls_*) | Preserve under neutral container `attributes['langchain_legacy']`; vendor emitter maps to proprietary keys. |
| Missing parent linkage in deeply nested chains | Ensure parent_run_id passed through all callbacks (LangChain provides); add defensive check & fallback to last seen root workflow. |
| Token counts missing for some providers | Leave fields None; metrics emitter tolerates absence. |
| Large input/output payload overhead | Implement truncation; disable capture if exceeds threshold. |

## 12. Acceptance Criteria
- No direct OpenTelemetry span creation calls remain in handler (except maybe for still-unconverted paths clearly flagged TODO).
- All LangChain lifecycle events create/update GenAI dataclasses and call appropriate handler methods.
- Tests green; manual example emits spans with semantic `gen_ai.*` attributes only (no `ls_*`, no `traceloop.*`).
- README changelog entries created per task.

## 13. Changelog (to be appended by implementer)
Format:
```
### [N]-[slug]
Status: planned|in-progress|done
Summary: ...
Details: ...
```
Initial planned entries:
1. entities-registry-intro (planned)
2. workflow-agent-task-mapping (planned)
3. llm-span-removal (planned)
4. error-path-refactor (planned)
5. tool-task-consolidation (planned)
6. metadata-truncation (planned)
7. tests-update (planned)
8. vendor-neutral-migration (planned)

### 1-entities-registry-intro
Status: done
Summary: Replace span bookkeeping with GenAI entity registry.
Details: Introduced `_entities`/`_llms` maps, lifecycle helpers, and removed direct span management.

### 2-workflow-agent-task-mapping
Status: done
Summary: Map LangChain chain/tool callbacks to Workflow/Agent/Task dataclasses.
Details: `on_chain_start`, `on_tool_start`, and related handlers now create/utilize GenAI types with parent propagation and payload capture.

### 3-llm-span-removal
Status: done
Summary: Stop direct span creation for LLM callbacks.
Details: Chat/completion handlers build `LLMInvocation` instances, manage prompt capture, and rely on telemetry handler for emission.

### 4-error-path-refactor
Status: done
Summary: Centralize error handling through GenAI fail lifecycle.
Details: `_handle_error` routes failures to `_fail_entity`, recording error metadata without span mutation.

### 5-tool-task-consolidation
Status: done
Summary: Normalize chain/tool callbacks into `Task` entities.
Details: Tool and nested chain flows share `_build_task`, including truncation-aware input/output capture.

### 6-metadata-truncation
Status: done
Summary: Add neutral truncation strategy for large payloads.
Details: Helpers enforce 8KB limits with `<truncated:N bytes>` markers and `orig_length` bookkeeping.

### 7-tests-update
Status: done
Summary: Align unit tests with refactored handler API.
Details: Updated expectations for agent operations, registry usage, and neutral metadata container.

### 8-vendor-neutral-migration
Status: done
Summary: Preserve LangChain legacy data without vendor-prefixed attributes.
Details: Attributes now use `langchain_legacy` buckets and neutral keys across entity lifecycles.

## 14. Prompt for AI Coder (Execute Incrementally)
You are a senior software engineer refactoring LangChain instrumentation to use `opentelemetry.util.genai` dataclasses and handler lifecycle.

> **Update cadence:** After every meaningful change (code, tests, or docs), append progress notes and refresh the status in this README to keep the plan current.

Context:
- Current callback handler file: `instrumentation-genai/opentelemetry-instrumentation-langchain-dev/src/opentelemetry/instrumentation/langchain/callback_handler.py` (see sections creating spans, maintaining `self.spans`, building agents, and LLM invocation logic).
- GenAI dataclasses: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/types.py`.
- Telemetry handler API: `opentelemetry.util.genai.handler.get_telemetry_handler()` and its `start_*`, `stop_*`, `fail_*` methods.

Requirements:
1. Replace direct span creation for new flows with dataclass creation + handler lifecycle calls.
2. Maintain parent-child relationships using `run_id` / `parent_run_id` fields.
3. Maintain agent context (agent name/id) on descendant `LLMInvocation`s.
4. Preserve legacy metadata in neutral container `attributes['langchain_legacy']` but do not emit vendor attrs on semantic spans.
5. Provide truncation for large serialized inputs/outputs (>8KB) with placeholder `"<truncated:N bytes>"` and store original length under `attributes['orig_length']`.
6. Remove or gate unused legacy span utilities.
7. Update tests referencing removed span attribute logic.
8. Update this README (Section 13) with each implemented step.
9. Keep commits logically small and labeled with changelog slug.

Definition of Done: See Acceptance Criteria (Section 12).

Proceed stepwise; after each step, run tests and update changelog.

## 15. Open Questions
- Should `ToolInvocation` become its own dataclass? (Defer).
- Workflow semantic conventions not yet standardized—OK to keep minimal for now.

---
End of document.
