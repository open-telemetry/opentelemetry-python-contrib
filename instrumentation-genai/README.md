# GenAI Instrumentations

This directory contains OpenTelemetry instrumentations for GenAI libraries, organized by category.

## Directory Structure

```
instrumentation-genai/
├── llm-clients/      # Direct LLM API client instrumentations
├── frameworks/       # Orchestration and agent framework instrumentations
├── vector-dbs/       # Vector database instrumentations
└── protocols/        # Protocol instrumentations (MCP, etc.)
```

## LLM Clients

Direct integrations with LLM provider APIs.

| Instrumentation | Supported Packages | Metrics | Default Mode |
| --------------- | ------------------ | ------- | ------------ |
| [opentelemetry-instrumentation-openai-v2](./llm-clients/opentelemetry-instrumentation-openai-v2) | openai >= 1.26.0 | Yes | metadata |
| [opentelemetry-instrumentation-anthropic](./llm-clients/opentelemetry-instrumentation-anthropic) | anthropic >= 0.3.0 | No | metadata |
| [opentelemetry-instrumentation-cohere](./llm-clients/opentelemetry-instrumentation-cohere) | cohere >= 5.0.0 | No | metadata |
| [opentelemetry-instrumentation-groq](./llm-clients/opentelemetry-instrumentation-groq) | groq >= 0.4.0 | No | metadata |
| [opentelemetry-instrumentation-mistralai](./llm-clients/opentelemetry-instrumentation-mistralai) | mistralai >= 0.1.0 | No | metadata |
| [opentelemetry-instrumentation-ollama](./llm-clients/opentelemetry-instrumentation-ollama) | ollama >= 0.1.0 | No | metadata |
| [opentelemetry-instrumentation-together](./llm-clients/opentelemetry-instrumentation-together) | together >= 0.2.0 | No | metadata |
| [opentelemetry-instrumentation-replicate](./llm-clients/opentelemetry-instrumentation-replicate) | replicate >= 0.15.0 | No | metadata |
| [opentelemetry-instrumentation-alephalpha](./llm-clients/opentelemetry-instrumentation-alephalpha) | aleph-alpha-client >= 2.0.0 | No | metadata |
| [opentelemetry-instrumentation-google-genai](./llm-clients/opentelemetry-instrumentation-google-genai) | google-genai >= 1.0.0 | No | metadata |
| [opentelemetry-instrumentation-bedrock](./llm-clients/opentelemetry-instrumentation-bedrock) | boto3 >= 1.28.0 | No | metadata |
| [opentelemetry-instrumentation-sagemaker](./llm-clients/opentelemetry-instrumentation-sagemaker) | boto3 >= 1.28.0 | No | metadata |
| [opentelemetry-instrumentation-vertexai](./llm-clients/opentelemetry-instrumentation-vertexai) | google-cloud-aiplatform >= 1.64 | No | metadata |
| [opentelemetry-instrumentation-watsonx](./llm-clients/opentelemetry-instrumentation-watsonx) | ibm-watsonx-ai >= 0.1.0 | No | metadata |

## Frameworks

Orchestration and agent frameworks that coordinate LLM calls.

| Instrumentation | Supported Packages | Metrics | Default Mode |
| --------------- | ------------------ | ------- | ------------ |
| [opentelemetry-instrumentation-langchain](./frameworks/opentelemetry-instrumentation-langchain) | langchain >= 0.1.0 | No | all |
| [opentelemetry-instrumentation-langgraph](./frameworks/opentelemetry-instrumentation-langgraph) | langgraph >= 0.2.0 | No | all |
| [opentelemetry-instrumentation-llamaindex](./frameworks/opentelemetry-instrumentation-llamaindex) | llama-index >= 0.10.0 | No | all |
| [opentelemetry-instrumentation-crewai](./frameworks/opentelemetry-instrumentation-crewai) | crewai >= 0.70.0 | No | all |
| [opentelemetry-instrumentation-haystack](./frameworks/opentelemetry-instrumentation-haystack) | haystack-ai >= 2.0.0 | No | all |
| [opentelemetry-instrumentation-agno](./frameworks/opentelemetry-instrumentation-agno) | agno >= 1.0.0 | No | all |
| [opentelemetry-instrumentation-openai-agents-v2](./frameworks/opentelemetry-instrumentation-openai-agents-v2) | openai-agents >= 0.3.3 | No | all |
| [opentelemetry-instrumentation-transformers](./frameworks/opentelemetry-instrumentation-transformers) | transformers >= 4.0.0 | No | all |

## Vector Databases

Vector database client instrumentations for RAG pipelines.

| Instrumentation | Supported Packages | Metrics |
| --------------- | ------------------ | ------- |
| [opentelemetry-instrumentation-chromadb](./vector-dbs/opentelemetry-instrumentation-chromadb) | chromadb >= 0.3.0 | No |
| [opentelemetry-instrumentation-pinecone](./vector-dbs/opentelemetry-instrumentation-pinecone) | pinecone-client >= 2.2.2 | No |
| [opentelemetry-instrumentation-qdrant](./vector-dbs/opentelemetry-instrumentation-qdrant) | qdrant-client >= 1.7.0 | No |
| [opentelemetry-instrumentation-milvus](./vector-dbs/opentelemetry-instrumentation-milvus) | pymilvus >= 2.4.1 | No |
| [opentelemetry-instrumentation-lancedb](./vector-dbs/opentelemetry-instrumentation-lancedb) | lancedb >= 0.9.0 | No |
| [opentelemetry-instrumentation-marqo](./vector-dbs/opentelemetry-instrumentation-marqo) | marqo >= 3.5.1 | No |
| [opentelemetry-instrumentation-weaviate](./vector-dbs/opentelemetry-instrumentation-weaviate) | weaviate-client >= 4.4.0 | No |

## Protocols

Protocol-level instrumentations.

| Instrumentation | Supported Packages | Metrics |
| --------------- | ------------------ | ------- |
| [opentelemetry-instrumentation-mcp](./protocols/opentelemetry-instrumentation-mcp) | mcp >= 1.0.0 | No |

## Capture Mode Configuration

GenAI instrumentations support per-package capture mode configuration:

```bash
# Per-package configuration (highest priority)
OTEL_INSTRUMENTATION_OPENAI_CAPTURE_MODE=metadata
OTEL_INSTRUMENTATION_LANGGRAPH_CAPTURE_MODE=all

# Global fallback
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE=metadata

# Legacy (backward compatible)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

### Capture Modes

| Mode | Description |
|------|-------------|
| `metadata` | Only metadata (token counts, model, finish reasons). No content, no log events. |
| `all` | Full capture including message content and log events. |

### Default Modes by Category

| Category | Default Mode | Rationale |
|----------|--------------|-----------|
| LLM Clients | `metadata` | Avoid capturing sensitive prompts/responses |
| Frameworks | `all` | Need full context for debugging workflows |
