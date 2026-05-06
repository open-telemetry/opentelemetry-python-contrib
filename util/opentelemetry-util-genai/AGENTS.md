# GenAI Utils — Agent and Contributor Guidelines

This package provides shared telemetry utilities for OpenTelemetry GenAI instrumentation.

## 1. Semantic Convention Compliance

No new telemetry without semconv. If a signal, attribute, or operation is not in the
[OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/), land the semconv change first.

All attributes, operation names, and span names must match semconv.

Use the semconv attribute modules — do not hardcode attribute name strings:

- `gen_ai.*` attributes: `opentelemetry.semconv._incubating.attributes.gen_ai_attributes`
- `server.*` attributes: `opentelemetry.semconv.attributes.server_attributes`
- `error.*` attributes: `opentelemetry.semconv.attributes.error_attributes`
- Other namespaces: use the corresponding module from `opentelemetry.semconv`

Shared attributes should behave consistently across invocation types (same conditions, same
defaults). If an attribute applies to more than one invocation per semconv, set it on all
applicable ones.

## 2. Invocation Lifecycle Pattern

Every new operation type must follow this pattern:

```python
invocation = handler.start_inference(provider, request_model, server_address=..., server_port=...)
invocation.temperature = ...
try:
    response = client.call(...)
    invocation.response_model_name = response.model
    invocation.finish_reasons = response.finish_reasons
    invocation.stop()
except Exception as exc:
    invocation.fail(exc)
    raise
```

Factory methods on `TelemetryHandler` (`handler.py`):

- `start_inference(provider, request_model, *, server_address, server_port)` → `InferenceInvocation`
- `start_embedding(provider, request_model, *, server_address, server_port)` → `EmbeddingInvocation`
- `start_tool(name, *, arguments, tool_call_id, tool_type, tool_description)` → `ToolInvocation`
- `start_workflow(name)` → `WorkflowInvocation`

Context manager equivalents (`handler.inference()`, `handler.embedding()`, `handler.tool()`,
`handler.workflow()`) are available when the span lifetime maps cleanly to a `with` block.

`start_*()` factories must map 1:1 to distinct semconv operation types (inference, embeddings,
tool execution, agent invocation, workflow invocation). Names must match the operation
unambiguously — for example, `create_agent` and `invoke_agent` are different operations, so a
single `start_agent()` would be ambiguous and is not acceptable. Add a new factory per operation
instead.

Factory names are Python-style singular verbs (`start_embedding`, `start_tool`); the op names
they map to follow semconv (`embeddings`, `tool execution`, future operations).

`start_*()` factories must accept all attributes that semconv marks as important for sampling
decisions as parameters, so they are on the span at creation time. Attributes that are also
marked required by semconv must be required parameters (no default value). Operation name
is usually hardcoded in specific invocation and does not need to be passed.

### Anti-patterns

**Never construct invocation types directly** (`InferenceInvocation(...)`, `ToolInvocation(...)`,
etc.) in instrumentation or production code — direct construction skips span creation and context
propagation, so all telemetry calls become no-ops. Always use `handler.start_*()`.

## 3. Exception Handling

- When catching exceptions from the underlying library to record telemetry, always re-raise
  the original exception unmodified.
- Do not raise new exceptions in telemetry code.

## 4. Performance

Keep the hot path tight:

- Avoid per-invocation allocations; do not accumulate state unboundedly.
- Skip content capture when content capture is disabled.
- Skip setting span-only attributes when the span is not recording.
- Still record attributes that feed metrics — metric recording is independent of span sampling.

## 5. DRY

Do not copy-paste logic across invocation types. Extract shared helpers.

## 6. Documentation

- Docstrings for invocation types and span/event helpers must include a link to the
  corresponding operation in the semconv spec.
- When adding or changing attributes, update the docstring to describe what is set and under
  what conditions (e.g., "set only when `server_address` is provided").

## 7. Tests

- Every new operation type or attribute change must have tests verifying the exact attribute
  names **and value types**, checked against the semconv spec.
- Cover all paths: success (`invocation.stop()`), failure (`invocation.fail(exc)`), and any
  conditional attribute logic (e.g., attributes set only when optional fields are populated).
- Tests live in `tests/` — follow existing patterns there.
- Don't call internal API in tests when the public API is available.

## 8. Python API Conventions

- Mark private modules with an underscore. Objects inside a private module should be prefixed
  with an underscore if they are not used outside that module.
- When adding fields or methods on invocation types (or anywhere in the public surface), push
  back hard: does this need to be public? If instrumentations don't need it, keep it internal
  (`_`-prefixed). Every public addition becomes a back-compat commitment.
- Before removing or renaming an object exposed publicly, deprecate it first with a note in the
  docstring pointing to the replacement.
