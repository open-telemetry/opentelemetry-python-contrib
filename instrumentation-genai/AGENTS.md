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

## 2. TelemetryHandler Initialization

Construct `TelemetryHandler` once inside `_instrument()`, passing all OTel providers and the
completion hook. Always prefer an explicitly injected hook (`kwargs.get("completion_hook")`)
over the entry-point hook loaded by `load_completion_hook()`, so test code can override the
hook without touching the environment.

```python
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

def _instrument(self, **kwargs):
    tracer_provider = kwargs.get("tracer_provider")
    meter_provider = kwargs.get("meter_provider")
    logger_provider = kwargs.get("logger_provider")

    handler = TelemetryHandler(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        completion_hook=kwargs.get("completion_hook") or load_completion_hook(),
    )
    # pass handler to each patch/wrapper function
```

## 3. Invocation Pattern

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

## 4. Exception Handling

- Do not add `raise {Error}` statements in instrumentation/telemetry code — validation belongs in
  tests and callers, not in the instrumentation layer.
- When catching exceptions from the underlying library to record telemetry, always re-raise
  the original exception unmodified.
