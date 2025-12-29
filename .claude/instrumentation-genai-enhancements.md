# Instrumentation GenAI Enhancements

This document describes the enhancements made to the `instrumentation-genai` packages for OpenAI and Weaviate, bringing feature parity with OpenLLMetry implementations.

## Overview

The following packages were enhanced:
- `opentelemetry-instrumentation-openai-v2`
- `opentelemetry-instrumentation-weaviate`

---

## OpenAI v2 Instrumentation Enhancements

### New APIs Instrumented

| API | Module | Operations |
|-----|--------|------------|
| **Legacy Completions** | `completions_patch.py` | `create`, `async create` |
| **Image Generation** | `images_patch.py` | `generate`, `async generate` |
| **Responses API** | `responses_patch.py` | `create`, `async create` |

### New Span Attributes

#### Request Attributes

| Attribute | Description | Type |
|-----------|-------------|------|
| `gen_ai.openai.request.user` | User identifier | string |
| `gen_ai.request.streaming` | Whether streaming is enabled | boolean |
| `gen_ai.openai.request.reasoning_effort` | Reasoning effort for o1/o3 models | string |
| `gen_ai.request.response_format.schema` | JSON schema for structured outputs | string (JSON) |
| `gen_ai.openai.api_base` | API base URL | string |
| `gen_ai.openai.api_version` | Azure API version | string |
| `gen_ai.request.tools.{i}.name` | Tool function name | string |
| `gen_ai.request.tools.{i}.description` | Tool function description | string |
| `gen_ai.request.tools.{i}.parameters` | Tool function parameters | string (JSON) |

#### Response Attributes

| Attribute | Description | Type |
|-----------|-------------|------|
| `llm.usage.total_tokens` | Total tokens (input + output) | int |
| `gen_ai.usage.input_tokens_details.cached` | Cached input tokens | int |
| `gen_ai.usage.output_tokens_details.reasoning` | Reasoning tokens (o1/o3) | int |
| `gen_ai.openai.response.system_fingerprint` | System fingerprint | string |

#### Content Capture Attributes (when enabled)

| Attribute | Description | API |
|-----------|-------------|-----|
| `gen_ai.request.messages` | Input messages as JSON | Chat Completions |
| `gen_ai.request.prompt` | Input prompt text | Legacy Completions |
| `gen_ai.request.input` | Input text | Embeddings |
| `gen_ai.request.instructions` | System instructions | Responses API |
| `gen_ai.response.content` | Generated response text | All APIs |

### Streaming Time Metrics

New histograms for streaming performance:

| Metric | Description |
|--------|-------------|
| `gen_ai.client.streaming.time_to_first_token` | Time from request to first token |
| `gen_ai.client.streaming.time_to_generate` | Time from first token to completion |

### Vendor Detection

Automatic detection of LLM provider from base URL:

| Vendor | URL Pattern |
|--------|-------------|
| `openai` | `api.openai.com` (default) |
| `azure` | `*.openai.azure.com` |
| `aws_bedrock` | `*.amazonaws.com`, `*bedrock*` |
| `google_vertex` | `*.googleapis.com`, `*vertex*` |
| `openrouter` | `openrouter.ai` |

### Trace Context Propagation

W3C trace context can be injected into OpenAI request headers:

```python
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# Enable trace context propagation
OpenAIInstrumentor(enable_trace_context_propagation=True).instrument()
```

This injects `traceparent` and `tracestate` headers for end-to-end tracing.

### Image Generation Attributes

| Attribute | Description |
|-----------|-------------|
| `gen_ai.request.image.size` | Image dimensions (e.g., "1024x1024") |
| `gen_ai.request.image.quality` | Quality setting (dall-e-3) |
| `gen_ai.request.image.style` | Style setting (dall-e-3) |
| `gen_ai.request.image.count` | Number of images to generate |
| `gen_ai.request.image.response_format` | Response format (url/b64_json) |
| `gen_ai.response.image.count` | Number of images returned |
| `gen_ai.response.created` | Creation timestamp |

### Responses API Attributes

| Attribute | Description |
|-----------|-------------|
| `gen_ai.request.modalities` | Output modalities |
| `gen_ai.openai.request.previous_response_id` | Previous response ID for multi-turn |
| `gen_ai.response.status` | Response status |

---

## Weaviate Instrumentation Enhancements

### V3 + V4 Client Support

The instrumentation now supports both Weaviate client versions:

#### V3 Methods (13 total)

| Category | Methods |
|----------|---------|
| Schema | `get`, `create_class`, `create`, `delete_class`, `delete_all` |
| Data | `create`, `validate`, `get` |
| Batch | `add_data_object`, `flush` |
| Query | `get`, `aggregate`, `raw` |

#### V4 Methods (16 total)

| Category | Methods |
|----------|---------|
| Collections | `get`, `create`, `create_from_dict`, `delete`, `delete_all` |
| Data | `insert`, `insert_many`, `replace`, `update` |
| Batch | `add_object` |
| Query | `fetch_object_by_id`, `fetch_objects`, `get` |
| GraphQL | `do` (GetBuilder, AggregateBuilder), `graphql_raw_query` |

### New Modules

#### `utils.py`

```python
# Prevents instrumentation errors from affecting the application
@dont_throw
def wrapped_function():
    ...

# Extracts and JSON-serializes arguments
getter = ArgsGetter(args, kwargs)
value = getter.get(0, "param_name")  # Gets by position or name

# Configuration for exception logging
Config.exception_logger = my_logger_function
```

#### `wrapper.py`

Factory pattern for operation-specific instrumentors:

```python
# Each operation type has its own instrumentor
instrumentor = InstrumentorFactory.get_instrumentor(method_info)
```

### Span Attributes per Operation

Each Weaviate operation captures relevant parameters as span attributes:

| Namespace | Attributes |
|-----------|------------|
| `db.weaviate.schema` | `class_name`, `schema_class`, `schema` |
| `db.weaviate.collections` | `name`, `config` |
| `db.weaviate.data` | `properties`, `references`, `uuid`, `vector` |
| `db.weaviate.batch` | `data_object`, `class_name`, `uuid`, `vector`, `tenant` |
| `db.weaviate.query` | `class_name`, `properties`, `gql_query`, `limit`, `offset`, `filters` |

### Exception Logging

Custom exception handler can be configured:

```python
def my_exception_handler(exception):
    # Log or handle instrumentation errors
    logging.error(f"Weaviate instrumentation error: {exception}")

WeaviateInstrumentor(exception_logger=my_exception_handler).instrument()
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Enable content capture | `false` |

### Enabling Content Capture

Set the environment variable to capture input/output content:

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

Or in Docker Compose:

```yaml
environment:
  - OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

---

## Files Modified/Created

### OpenAI v2

| File | Action | Description |
|------|--------|-------------|
| `__init__.py` | Modified | Added new API wrappers, trace context config |
| `utils.py` | Modified | Vendor detection, new attributes, trace propagation, content capture |
| `patch.py` | Modified | Streaming time tracking, content capture |
| `instruments.py` | Modified | Streaming time histograms |
| `completions_patch.py` | Created | Legacy Completions API |
| `images_patch.py` | Created | Image Generation API |
| `responses_patch.py` | Created | Responses API |

### Weaviate

| File | Action | Description |
|------|--------|-------------|
| `__init__.py` | Modified | V3 methods, combined V3+V4 |
| `utils.py` | Created | `dont_throw`, `ArgsGetter`, `Config` |
| `wrapper.py` | Created | Instrumentor factory pattern |

---

## Example Usage

### OpenAI with Full Instrumentation

```python
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

# Enable all features
OpenAIInstrumentor(
    enable_trace_context_propagation=True
).instrument()

# Set environment variable for content capture
# OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

### Weaviate with Exception Logging

```python
from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor

def log_errors(e):
    print(f"Instrumentation error: {e}")

WeaviateInstrumentor(exception_logger=log_errors).instrument()
```

---

## Compatibility

- **OpenAI SDK**: >= 1.26.0
- **Weaviate Client**: v3.x and v4.x
- **OpenTelemetry API**: ~= 1.37
- **OpenTelemetry Instrumentation**: ~= 0.58b0
