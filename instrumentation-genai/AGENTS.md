# GenAI Instrumentation — Agent and Contributor Guidelines

Instrumentation packages here wrap specific libraries (OpenAI, Anthropic, etc.) and bridge
them to the shared telemetry layer in `util/opentelemetry-util-genai`.

## 1. Instrumentation Layer Boundary

Do not call OpenTelemetry APIs (`tracer`, `meter`, `span`, event APIs) directly.
Always go through `TelemetryHandler` and the invocation objects it returns.

This layer is responsible only for:

- Patching the library
- Parsing library-specific input/output into invocation fields

Everything else (span creation, metric recording, event emission, context propagation)
belongs in `util/opentelemetry-util-genai`.

## 2. Invocation Pattern

Use `start_*()` and control span lifetime manually:

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

## 3. Semantic conventions

Attributes, spans, events, and metrics follow the
[GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai).
Do not emit signals that are not covered by semconv.

## 4. Tests

- Use VCR cassettes for provider calls. Do not skip tests when an API key is missing.
- For every public API touched, cover sync/async and streaming/non-streaming variants when
  both exist.
- Cover happy path and error scenarios, at minimum: provider error / endpoint unavailable,
  stream interrupted by network, stream closed early by the caller.

## 5. Examples

New instrumentations ship a minimal example under the package's `examples/` directory, with
both a `manual/` setup and a `zero-code/` (auto-instrumentation) variant.
