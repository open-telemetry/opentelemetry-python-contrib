# Anthropic & ChromaDB Instrumentation Enhancements

This document describes the enhancements made to bring Anthropic instrumentation to full implementation and the addition of ChromaDB as a new instrumentation package.

## Overview

The following packages were enhanced/created:
- `opentelemetry-instrumentation-anthropic` - Full implementation (was skeleton)
- `opentelemetry-instrumentation-chromadb` - New package

---

## Anthropic Instrumentation

### Status: Fully Implemented

The Anthropic instrumentation was previously a skeleton with no actual patching. It now has full feature parity with the OpenLLMetry implementation.

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `__init__.py` | Modified | Full instrumentor with WRAPPED_METHODS, patching/unpatching |
| `patch.py` | Modified | Wrapper functions for all API methods |
| `utils.py` | Created | Utility functions, attribute helpers, content capture |
| `instruments.py` | Created | Metrics instruments (histograms) |
| `streaming.py` | Created | Stream wrapper classes |
| `pyproject.toml` | Modified | Added wrapt dependency |

### APIs Instrumented

| API | Module | Methods |
|-----|--------|---------|
| **Messages API** | `anthropic.resources.messages` | `create`, `stream` (sync & async) |
| **Beta Messages** | `anthropic.resources.beta.messages.messages` | `create`, `stream` (sync & async) |
| **Bedrock SDK** | `anthropic.lib.bedrock._beta_messages` | `create`, `stream` (sync & async) |

### Span Attributes

#### Request Attributes

| Attribute | Description | Type |
|-----------|-------------|------|
| `gen_ai.system` | "anthropic" | string |
| `gen_ai.operation.name` | "chat" | string |
| `gen_ai.request.model` | Model name | string |
| `gen_ai.request.max_tokens` | Maximum tokens | int |
| `gen_ai.request.temperature` | Temperature | float |
| `gen_ai.request.top_p` | Top-p sampling | float |
| `gen_ai.request.streaming` | Whether streaming | boolean |
| `gen_ai.request.stop_sequences` | Stop sequences | list |
| `gen_ai.request.tools.{i}.name` | Tool name | string |
| `gen_ai.request.tools.{i}.description` | Tool description | string |
| `gen_ai.request.tools.{i}.parameters` | Tool schema (JSON) | string |
| `server.address` | Server hostname | string |
| `server.port` | Server port | int |

#### Response Attributes

| Attribute | Description | Type |
|-----------|-------------|------|
| `gen_ai.response.model` | Actual model used | string |
| `gen_ai.response.id` | Response ID | string |
| `gen_ai.response.finish_reasons` | Stop reason | list |
| `gen_ai.usage.input_tokens` | Input token count | int |
| `gen_ai.usage.output_tokens` | Output token count | int |
| `llm.usage.total_tokens` | Total tokens | int |
| `gen_ai.usage.input_tokens_details.cached` | Cached input tokens | int |
| `gen_ai.usage.cache_creation_input_tokens` | Cache creation tokens | int |

#### Content Capture (when enabled)

| Attribute | Description |
|-----------|-------------|
| `gen_ai.request.messages` | Input messages as JSON |
| `gen_ai.response.content` | Response content |

### Metrics

| Metric | Description |
|--------|-------------|
| `gen_ai.client.operation.duration` | Operation duration histogram |
| `gen_ai.client.token.usage` | Token usage histogram |
| `gen_ai.client.streaming.time_to_first_token` | Time to first token |
| `gen_ai.client.streaming.time_to_generate` | Time from first token to completion |

### Streaming Support

Full streaming support with wrapper classes:

- `AnthropicStream` - Sync stream iterator wrapper
- `AnthropicAsyncStream` - Async stream iterator wrapper
- `WrappedMessageStreamManager` - Context manager for `Messages.stream()`
- `WrappedAsyncMessageStreamManager` - Async context manager

Anthropic streaming events handled:
1. `message_start` - Model, usage, message ID
2. `content_block_start` - Text/tool_use/thinking block start
3. `content_block_delta` - Incremental content
4. `message_delta` - Final usage, stop reason
5. `message_stop` - Stream complete

### Special Features

- **Thinking content blocks**: Extended thinking captured as `[Thinking]: ...`
- **Tool use**: Full tool call capturing with arguments
- **Prompt caching**: Cache read and creation token tracking
- **with_raw_response**: Automatic parsing of wrapped responses
- **Error handling**: `dont_throw` decorator prevents instrumentation errors from affecting the application

---

## ChromaDB Instrumentation (New Package)

### Status: New Implementation

ChromaDB is a vector database commonly used in GenAI/RAG applications. This new package provides full instrumentation.

### Package Location

`instrumentation-genai/opentelemetry-instrumentation-chromadb/`

### Files Created

| File | Description |
|------|-------------|
| `pyproject.toml` | Hatchling build config, entry points |
| `README.rst` | Package documentation |
| `version.py` | Version "2.0b0.dev" |
| `package.py` | `_instruments = ("chromadb >= 0.3.0",)` |
| `semconv.py` | Local semantic conventions (40+ attributes) |
| `utils.py` | `dont_throw`, `Config`, helper functions |
| `wrapper.py` | Wrapper functions, attribute setters |
| `__init__.py` | `ChromaInstrumentor` class |

### Methods Instrumented

#### Collection Methods (8 total)

| Method | Span Name | Description |
|--------|-----------|-------------|
| `add` | `chroma.add` | Add documents/embeddings |
| `get` | `chroma.get` | Retrieve documents by ID |
| `peek` | `chroma.peek` | Preview collection |
| `query` | `chroma.query` | Vector similarity search |
| `modify` | `chroma.modify` | Modify collection metadata |
| `update` | `chroma.update` | Update documents |
| `upsert` | `chroma.upsert` | Insert or update |
| `delete` | `chroma.delete` | Delete documents |

#### Internal Methods (1 total)

| Method | Span Name | Description |
|--------|-----------|-------------|
| `SegmentAPI._query` | `chroma.query.segment._query` | Internal query with embeddings |

### Span Attributes

#### Universal Attributes

| Attribute | Value |
|-----------|-------|
| `db.system` | "chromadb" |
| `db.operation` | Method name |

#### Add Operation

| Attribute | Description |
|-----------|-------------|
| `db.chroma.add.ids_count` | Number of IDs |
| `db.chroma.add.embeddings_count` | Number of embeddings |
| `db.chroma.add.metadatas_count` | Number of metadata objects |
| `db.chroma.add.documents_count` | Number of documents |

#### Get Operation

| Attribute | Description |
|-----------|-------------|
| `db.chroma.get.ids_count` | Number of IDs to fetch |
| `db.chroma.get.where` | Where filter (string) |
| `db.chroma.get.limit` | Result limit |
| `db.chroma.get.offset` | Result offset |
| `db.chroma.get.where_document` | Document filter |
| `db.chroma.get.include` | Fields to include |

#### Query Operation

| Attribute | Description |
|-----------|-------------|
| `db.chroma.query.embeddings_count` | Number of query embeddings |
| `db.chroma.query.texts_count` | Number of query texts |
| `db.chroma.query.n_results` | Number of results requested |
| `db.chroma.query.where` | Where filter |
| `db.chroma.query.where_document` | Document filter |
| `db.chroma.query.include` | Fields to include |

#### Update/Upsert Operations

| Attribute | Description |
|-----------|-------------|
| `db.chroma.{op}.ids_count` | Number of IDs |
| `db.chroma.{op}.embeddings_count` | Number of embeddings |
| `db.chroma.{op}.metadatas_count` | Number of metadata objects |
| `db.chroma.{op}.documents_count` | Number of documents |

#### Delete Operation

| Attribute | Description |
|-----------|-------------|
| `db.chroma.delete.ids_count` | Number of IDs |
| `db.chroma.delete.where` | Where filter |
| `db.chroma.delete.where_document` | Document filter |

### Events

#### Query Result Events

For each result from a `query()` call:

```
Event: "db.query.result"
Attributes:
  - db.query.result.id: Result document ID
  - db.query.result.distance: Similarity distance
  - db.query.result.document: Retrieved document text
  - db.query.result.metadata: Associated metadata (JSON)
```

#### Embedding Vector Events

For internal `_query()` method:

```
Event: "db.query.embeddings"
Attributes:
  - db.query.embeddings.vector: Embedding vector (JSON array)
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Enable content capture | `false` |

### Enabling Content Capture

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

---

## Example Usage

### Anthropic with Full Instrumentation

```python
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
import anthropic

# Enable instrumentation
AnthropicInstrumentor().instrument()

# Use Anthropic client
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)

# Streaming
with client.messages.stream(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Count to 5"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### ChromaDB with Instrumentation

```python
from opentelemetry.instrumentation.chromadb import ChromaInstrumentor
import chromadb

# Enable instrumentation
ChromaInstrumentor().instrument()

# Use ChromaDB
client = chromadb.Client()
collection = client.create_collection("my_collection")

# Add documents
collection.add(
    documents=["Hello, world!", "Goodbye, world!"],
    metadatas=[{"source": "greeting"}, {"source": "farewell"}],
    ids=["id1", "id2"]
)

# Query
results = collection.query(
    query_texts=["Hello"],
    n_results=1
)
```

### Exception Logging

Both instrumentors support custom exception logging:

```python
def my_exception_handler(e):
    print(f"Instrumentation error: {e}")

AnthropicInstrumentor(exception_logger=my_exception_handler).instrument()
ChromaInstrumentor(exception_logger=my_exception_handler).instrument()
```

---

## Compatibility

- **Anthropic SDK**: >= 0.3.0
- **ChromaDB**: >= 0.3.0
- **OpenTelemetry API**: ~= 1.37
- **OpenTelemetry Instrumentation**: ~= 0.58b0
- **Python**: >= 3.9

---

## References

These implementations are based on the OpenLLMetry packages:
- `openllmetry/packages/opentelemetry-instrumentation-anthropic/`
- `openllmetry/packages/opentelemetry-instrumentation-chromadb/`

Adapted to follow the patterns established in `instrumentation-genai/`:
- `opentelemetry-instrumentation-openai-v2` (for Anthropic patterns)
- `opentelemetry-instrumentation-weaviate` (for ChromaDB patterns)
