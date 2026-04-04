# GenAI Utils — Agent and Contributor Guidelines

This package provides shared telemetry utilities for OpenTelemetry GenAI instrumentation.

## 1. Semantic Convention Compliance

All attributes, operation names, and span names must match the
[OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/)
exactly.

Use the appropriate semconv attribute modules — do not hardcode attribute name strings:

- `gen_ai.*` attributes: `opentelemetry.semconv._incubating.attributes.gen_ai_attributes`
- `server.*` attributes: `opentelemetry.semconv.attributes.server_attributes`
- `error.*` attributes: `opentelemetry.semconv.attributes.error_attributes`
- Other namespaces: use the corresponding module from `opentelemetry.semconv`

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

### Anti-patterns

**Never construct invocation types directly** (`InferenceInvocation(...)`, `ToolInvocation(...)`,
etc.) in instrumentation or production code — direct construction skips span creation and context
propagation, so all telemetry calls become no-ops. Always use `handler.start_*()`.

## 3. Exception Handling

- Do not add `raise {Error}` statements to `handler.py` or `types.py` — validation belongs in
  tests and callers, not telemetry internals.
- When catching exceptions from the underlying library to record telemetry, always re-raise
  the original exception unmodified.

## 4. Documentation

- Docstrings for invocation types and span/event helpers must include a link to the
  corresponding operation in the semconv spec.
- When adding or changing attributes, update the docstring to describe what is set and under
  what conditions (e.g., "set only when `server_address` is provided").

## 5. Tests

- Every new operation type or attribute change must have tests verifying the exact attribute
  names and values produced, checked against the semconv spec.
- Cover all paths: success (`invocation.stop()`), failure (`invocation.fail(exc)`), and any
  conditional attribute logic (e.g., attributes set only when optional fields are populated).
- Tests live in `tests/` — follow existing patterns there.
- Don't call internal API in tests when the public API is available.

## 6. Python API Conventions

- Mark private modules with an underscore.
- Objects inside of a private module should be prefixed with underscopre if they
  are not used outside the that module.
- Before removing or renaming an object exposed publicly, deprecate it first with
  `@deprecated("... Use X instead.")` pointing to the replacement;
