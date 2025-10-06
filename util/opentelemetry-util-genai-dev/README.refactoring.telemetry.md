# GenAI Telemetry Refactoring: LLMInvocation Span Flavors (Semantic Conventions vs Traceloop)

> Status: DRAFT (bootstrap commit)
> Owner: (add GitHub handle)
> Last Updated: 2025-10-06

This document tracks the refactoring to unify the `LLMInvocation` data model and emitters so that:

1. Fields defined in the OpenTelemetry GenAI semantic conventions are explicitly marked in `LLMInvocation` with `metadata={"semconv": <attribute>}`.
2. The same field is reused for both semantic-convention spans and the Traceloop compatibility flavor—no duplication.
3. Traceloop-only needs are satisfied via optional, clearly separated fields (or via `attributes` mapping) without introducing parallel core fields that duplicate semconv meaning.
4. The span emitters:
   - `span.py` (semantic conv flavor) emits ONLY semconv-approved `gen_ai.*` attributes (plus minimal framework/provider bridging already in semconv).
   - `traceloop.py` emits ONLY the legacy Traceloop-style flattened attributes (prefixed with `traceloop.` or mapped keys) and the subset of `gen_ai.*` it currently sets for backward compatibility.
5. Content (messages) emission logic respects `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` and mode env vars for span vs event capture.

---
## 1. Reference Samples

### 1.1 Semantic Conventions Sample (Observed)
```
Attributes:
 callback.name=ChatOpenAI
 span.kind=llm
 callback.id=["langchain","chat_models","openai","ChatOpenAI"]
 ls_model_type=chat               (non-semconv; legacy/langchain metadata)
 ls_temperature=0.1               (duplicate of gen_ai.request.temperature)
 ls_stop=["\n","Human:","AI:"]   (duplicate of gen_ai.request.stop_sequences)
 stream=false
 user={"appkey": "..."}
 max_completion_tokens=100        (duplicate of gen_ai.request.max_tokens)
 _type=openai-chat
 gen_ai.framework=langchain
 gen_ai.provider.name=openai
 gen_ai.request.model=gpt-4.1
 gen_ai.operation.name=chat
 gen_ai.response.model=gpt-4.1-2025-04-14
 gen_ai.response.id=chatcmpl-...
 gen_ai.usage.input_tokens=42
 gen_ai.usage.output_tokens=77
 gen_ai.request.temperature=0.1
 gen_ai.request.top_p=0.9
 gen_ai.request.frequency_penalty=0.5
 gen_ai.request.presence_penalty=0.5
 gen_ai.request.stop_sequences=["\n","Human:","AI:"]
 gen_ai.request.max_tokens=100
 gen_ai.request.seed=100
```

### 1.2 Traceloop Sample (Observed)
```
Attributes:
 traceloop.association.properties.ls_provider=openai
 traceloop.association.properties.ls_model_name=gpt-4.1
 traceloop.association.properties.ls_model_type=chat
 traceloop.association.properties.ls_temperature=0.1
 traceloop.association.properties.ls_max_tokens=100
 traceloop.association.properties.ls_stop=["\n","Human:","AI:"]
 llm.usage.total_tokens=57 (Traceloop style)
 llm.request.type=chat
 gen_ai.system=openai
 gen_ai.request.model=gpt-4.1
 gen_ai.request.max_tokens=100
 gen_ai.request.temperature=0.1
 gen_ai.request.top_p=0.9
 gen_ai.prompt.0.role=system
 gen_ai.prompt.0.content=...
 gen_ai.prompt.1.role=user
 gen_ai.prompt.1.content=...
 gen_ai.response.model=gpt-4.1-2025-04-14
 gen_ai.response.id=chatcmpl-...
 gen_ai.usage.prompt_tokens=47
 gen_ai.usage.completion_tokens=10
 gen_ai.usage.cache_read_input_tokens=0
 gen_ai.completion.0.content=...
 gen_ai.completion.0.role=assistant
```

---
## 2. Existing `LLMInvocation` Fields (Current Code)
Source: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/types.py`

Core semconv mapped fields already present:
- provider (GEN_AI_PROVIDER_NAME)
- agent_name / agent_id / system / conversation_id / data_source_id
- request_model (GEN_AI_REQUEST_MODEL)
- operation (GEN_AI_OPERATION_NAME)
- response_model_name (GEN_AI_RESPONSE_MODEL)
- response_id (GEN_AI_RESPONSE_ID)
- input_tokens (GEN_AI_USAGE_INPUT_TOKENS)
- output_tokens (GEN_AI_USAGE_OUTPUT_TOKENS)
- request_temperature / top_p / top_k / frequency_penalty / presence_penalty
- request_stop_sequences / max_tokens / choice_count / seed / encoding_formats
- output_type (GEN_AI_OUTPUT_TYPE)
- response_finish_reasons (GEN_AI_RESPONSE_FINISH_REASONS)
- request_service_tier / response_service_tier / response_system_fingerprint (OpenAI specific semantics)
- request_functions (structured -> semantic conv function.* via emitter)
- input_messages / output_messages (captured into span attributes only when content capture is enabled)

Non-semconv / internal convenience fields:
- framework (currently emitted as `gen_ai.framework` manually)
- chat_generations (not used by emitters – candidate for removal or deprecation)
- attributes (arbitrary user / instrumentation extras, currently filtered in span emitter allowing `gen_ai.` + `traceloop.` prefixes on finish)

Gaps relative to samples:
- Traceloop-specific association properties (ls_provider, ls_model_name, ls_model_type, ls_temperature, ls_max_tokens, ls_stop) are NOT distinct first-class fields—they arrive as metadata and end up in `attributes`.
- Traceloop wants flattened enumerated prompt/completion content (`gen_ai.prompt.N.*`, `gen_ai.completion.N.*`) whereas current semconv flavor emits aggregated JSON arrays (`gen_ai.input.messages`, `gen_ai.output.messages`). Refactoring direction: keep semconv representation in semconv span; produce enumerated form only in traceloop emitter (derivable from existing `input_messages` / `output_messages`).
- Need to ensure ls_* aliases do NOT duplicate semconv attributes in the semconv span flavor (they should be ignored / excluded there after refactor).

---
## 3. Refactoring Objectives

A. Data Model
- Ensure every semconv attribute we emit is backed by a dedicated dataclass field with `metadata={'semconv': ...}` (already largely true).
- Remove / deprecate `chat_generations`: not required—`output_messages` suffices.
- Optionally add explicit optional fields ONLY if Traceloop requires something not derivable from existing semconv fields. (Current assessment: no new core fields needed; traceloop can compute from existing ones.)
- Mark `framework` either: (1) map to a future semconv if defined OR (2) keep as non-semconv; ensure span emitter does not treat it like a semconv attribute (only set if still desired).

B. Span Emitter (`span.py`)
- Restrict attribute emission to:
  * dataclass semconv attributes via `semantic_convention_attributes()`.
  * explicit provider/framework bridging if approved (provider already semconv; framework maybe removed or feature-flagged).
  * function definitions using semantic conv helper.
- Remove emission of arbitrary `attributes` unless those keys start with `gen_ai.` AND correspond to recognized spec fields (to avoid leaking `ls_*`).
- Add content message emission: when `CAPTURE_MESSAGE_CONTENT=true` AND mode is SPAN or SPAN_AND_EVENT, set `gen_ai.input.messages` and `gen_ai.output.messages`. (Currently done; just guard mode logic once integrated with env evaluation.)

C. Traceloop Emitter (`traceloop.py`)
- Stop copying non-semconv arbitrary attributes into `traceloop.*` unless they are explicitly part of traceloop flavor contract.
- Derive enumerated prompt/completion attributes from `input_messages` / `output_messages`.
- Include request parameter semconv equivalents but NOT duplicate with `ls_` naming inside semantic conv span flavor.
- Provide mapping table (internal) so additions remain consistent.

D. LangChain Callback Handler
- Populate only semconv-aligned fields on `LLMInvocation` for core params.
- Move ls_* vendor/legacy fields strictly into `attributes` (NOT new dataclass fields) – for consumption exclusively by traceloop emitter if needed.
- Remove population of `chat_generations`.
- Ensure request_* fields are set directly (temperature, top_p, etc.) and not left duplicated in `attributes` as raw invocation values.

---
## 4. Mapping Table (Authoritative During Refactor)
| Concept | SemConv Attribute | LLMInvocation Field | Traceloop Flavor Attribute | Source / Derivation | Action |
|---------|-------------------|---------------------|----------------------------|---------------------|--------|
| Provider | gen_ai.provider.name | provider | traceloop.association.properties.ls_provider | metadata/provider | Keep field; traceloop duplicates via mapping |
| Model (request) | gen_ai.request.model | request_model | traceloop.association.properties.ls_model_name | invocation params | Keep field |
| Operation | gen_ai.operation.name | operation | llm.request.type (chat) | constant default | Keep field; traceloop sets llm.request.type=operation |
| Response Model | gen_ai.response.model | response_model_name | gen_ai.response.model | response payload | Keep field |
| Response ID | gen_ai.response.id | response_id | gen_ai.response.id | response payload | Keep field |
| Input Tokens | gen_ai.usage.input_tokens | input_tokens | gen_ai.usage.prompt_tokens | usage.prompt_tokens | Keep field; traceloop rename mapping |
| Output Tokens | gen_ai.usage.output_tokens | output_tokens | gen_ai.usage.completion_tokens | usage.completion_tokens | Keep field; traceloop rename mapping |
| Seed | gen_ai.request.seed | request_seed | (same, optional) | params | Keep field |
| Temperature | gen_ai.request.temperature | request_temperature | traceloop.association.properties.ls_temperature (and semconv) | params | Keep field; traceloop alias only |
| Top P | gen_ai.request.top_p | request_top_p | (same) | params | Keep field |
| Top K | gen_ai.request.top_k | request_top_k | (same) | params | Keep field |
| Frequency Penalty | gen_ai.request.frequency_penalty | request_frequency_penalty | (same) | params | Keep field |
| Presence Penalty | gen_ai.request.presence_penalty | request_presence_penalty | (same) | params | Keep field |
| Stop Seqs | gen_ai.request.stop_sequences | request_stop_sequences | traceloop.association.properties.ls_stop | params | Keep field; traceloop alias only |
| Max Tokens | gen_ai.request.max_tokens | request_max_tokens | traceloop.association.properties.ls_max_tokens | params | Keep field |
| Choice Count | gen_ai.request.choice_count | request_choice_count | (same) | params | Keep field |
| Encoding Formats | gen_ai.request.encoding_formats | request_encoding_formats | (same) | params | Keep field |
| Output Type | gen_ai.output.type | output_type | (same) | response | Keep field |
| Finish Reasons | gen_ai.response.finish_reasons | response_finish_reasons | (same) | response | Keep field |
| Messages Input | gen_ai.input.messages | input_messages | gen_ai.prompt.N.* (enumerated) | from list | Keep field; enumeration only in traceloop |
| Messages Output | gen_ai.output.messages | output_messages | gen_ai.completion.N.* | from list | Keep field; enumeration only in traceloop |
| Framework | (none today official) | framework | (maybe traceloop.association.properties.framework) | internal | Consider feature flag or leave non-semconv |
| Agent linking | gen_ai.agent.name/id | agent_name / agent_id | (same) | parent agent | Keep fields |

---
## 5. Concrete Refactoring Tasks (To Be Executed by AI Coder Agent)

### Data Model (`types.py`)
- [ ] Remove unused `chat_generations` field from `LLMInvocation` (or mark deprecated comment first if backward compat needed).
- [ ] Ensure docstring clarifies that only semconv fields have `metadata['semconv']`.
- [ ] (Optional) Add comment that Traceloop flavor derives enumerated prompt/completion attributes; no extra fields required.

### Span Emitter (`span.py`)
- [ ] Restrict finish-time attribute application: when adding `attributes` filter only keys starting with `gen_ai.` AND present in spec OR part of allowed supplemental list (`gen_ai.framework` maybe) – exclude `ls_*`.
- [ ] Do NOT propagate any `traceloop.*` keys onto semconv span.
- [ ] Integrate content mode logic (SPAN vs EVENTS vs BOTH) by reading existing content capture config (if not already) – currently binary `_capture_content`; extend to accept mode enumeration (wired later by handler/env).

### Traceloop Emitter (`traceloop.py`)
- [ ] Stop indiscriminate copying of every non `gen_ai.` attribute; introduce whitelist mapping for legacy `ls_*` -> `traceloop.association.properties.*`.
- [ ] Add derivation of enumerated prompt attributes `gen_ai.prompt.{i}.role` / `gen_ai.prompt.{i}.content` from `input_messages` if capture enabled and mode requires spans or events.
- [ ] Add derivation of enumerated completion attributes `gen_ai.completion.{i}.role` / `gen_ai.completion.{i}.content` from `output_messages` similarly.
- [ ] Map semconv token usage to traceloop names (prompt/completion, plus compute total if needed: `llm.usage.total_tokens = prompt+completion`).

### LangChain Callback Handler
- [ ] Remove assignment/population of any deprecated `chat_generations` use.
- [ ] After extracting request params, ensure duplicates are removed from the `attributes` dict (no `temperature`, etc.) to avoid reintroducing non-semconv differences.
- [ ] Insert an explicit cleanup step removing `ls_temperature`, `ls_model_type`, etc. after mapping to semconv fields.

### Configuration & Env
- [ ] Introduce/confirm env var parsing for content mode (NONE | SPAN | EVENT | SPAN_AND_EVENT) at util handler level; propagate into both emitters.

### Tests
- [ ] Update existing tests expecting `ls_temperature` etc. on semconv spans—they should now expect ONLY semconv equivalents.
- [ ] Add tests to validate traceloop flavor still produces enumerated prompt/completion fields.
- [ ] Add regression test ensuring no `ls_*` attributes leak into semantic-convention span flavor.

---
## 6. Open Questions / Assumptions
- Assumption: Backward compatibility does not require preserving `chat_generations`; callers rely on `output_messages`.
- Assumption: It is acceptable to drop `ls_*` attributes from semconv spans (they remain accessible via traceloop flavor if that emitter is enabled).
- Assumption: `gen_ai.framework` is temporarily retained; may become an official semconv or be removed later.
- Question: Should `user` (custom JSON) be standardized? (Deferred – not part of current semconv set.)

---
## 7. Changelog (Execution Queue for AI Coder Agent)
Entries will be appended here as PR-sized units. Follow format:
```
### [ID]-[short-slug]
Status: (planned|in-progress|done)
Summary: One-line change summary.
Details:
- Bullet specifics
Migration Notes (if any):
```

Planned initial entries:
1. Remove chat_generations & tighten span emitter attribute filtering.
2. Add content mode enumeration and update emitters.
3. Refactor traceloop emitter for whitelist + enumerated messages.
4. Clean callback handler duplicate attributes; remove ls_* leakage.
5. Update tests & add regression coverage.

---
## 8. Agent Directives (You Are The Senior Software Engineer)
When implementing tasks from Section 5:
- Apply one logical group per commit / patch to ease review.
- Always update this README section 7 (Changelog) marking entries status transitions.
- Maintain zero failing tests; if a test requires rewrite, adjust fixture/matcher rather than reintroducing deprecated attributes.
- Enforce: semantic-convention span MUST NOT contain `ls_*` or `traceloop.*` attributes post-refactor.
- Enforce: traceloop span MUST NOT add new `gen_ai.*` attributes beyond those in sample (provider, request.model, response.*, usage.* basic, request param semconvs). Avoid `gen_ai.input.messages` / `gen_ai.output.messages` (those are semconv JSON forms) – use enumerated prompt/completion fields instead.
- Provide mapping utilities if repetition appears.

### Coding Guardrails
- Prefer small helper functions for: enumerating prompt/completion fields, filtering semconv attributes, mapping ls_* to traceloop association properties.
- Add docstrings for any new helpers.
- Keep dataclass field ordering stable except for removed fields to minimize diff noise.

### Definition of Done
- All tasks in Section 5 have corresponding completed changelog entries.
- Running LangChain example with both span flavors produces:
  * Semconv span: ONLY `gen_ai.*` spec fields + allowed extras (`gen_ai.framework` if retained) and NO `ls_*`.
  * Traceloop span: Legacy attributes and enumerated prompt/completion fields; no JSON aggregated message attributes.
- Tests updated and green.

---
## 9. Next Steps After Core Refactor (Not In Scope Yet)
- Potential normalization of evaluation metrics across flavors.
- Consolidate environment variable parsing into a single config object shared by emitters.
- Add metrics alignment for total tokens vs prompt/completion tokens.

---
## 10. Maintaining This Document
- Treat as the source of truth for the refactor state.
- Each code change MUST update Section 7 (Changelog) before merge.
- Do not remove historical entries; append new ones chronologically.
- Keep Open Questions updated; move resolved items into tasks / changelog entries.

---
(End of document)
