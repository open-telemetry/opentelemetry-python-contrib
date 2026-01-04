# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Repository Overview

OpenTelemetry Python Contrib monorepo with 50+ auto-instrumentation libraries for Python.

## Commands

```bash
# Setup
pip install tox tox-uv && uv sync && pre-commit install

# Tests
tox -e py312-test-instrumentation-openai-v2-latest   # GenAI package
tox -re py312-test-instrumentation-requests          # -r recreates env

# Lint
tox -e ruff
```

## Package Structure

```
instrumentation/                    # Standard instrumentations (Flask, Django, etc.)
instrumentation-genai/              # GenAI instrumentations
  ├── llm-clients/                  # OpenAI, Anthropic, VertexAI, Bedrock, Cohere, Groq
  ├── frameworks/                   # LangChain, LangGraph, CrewAI, Haystack, LlamaIndex
  ├── vector-dbs/                   # ChromaDB, Pinecone, Milvus, Qdrant, Weaviate
  └── protocols/                    # MCP
opentelemetry-instrumentation/      # Base framework (BaseInstrumentor)
util/                               # Shared utilities
```

## GenAI Instrumentation

### Capture Modes

| Mode | Description | Default For |
|------|-------------|-------------|
| `metadata` | Token counts, model, finish reasons only | LLM clients |
| `all` | Full content including messages and tool details | Frameworks |

**Environment variables:**
```bash
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE=metadata|all     # Global
OTEL_INSTRUMENTATION_OPENAI_CAPTURE_MODE=metadata        # Per-package (higher priority)
```

**Resolution order:** Package-specific → Global → Legacy → Package default

### Semantic Conventions

- Use `gen_ai.*` namespace for attributes
- Use `opentelemetry.semconv._incubating.attributes.gen_ai_attributes`
- NEVER use `traceloop.*` or other vendor namespaces

### Package Layout

```
instrumentation-genai/{category}/opentelemetry-instrumentation-{name}/
├── src/opentelemetry/instrumentation/{name}/
│   ├── __init__.py      # Main Instrumentor (extends BaseInstrumentor)
│   ├── version.py
│   ├── package.py       # _instruments tuple
│   ├── patch.py         # Wrapper functions
│   └── utils.py
├── tests/
└── pyproject.toml
```

### Reference Implementation

See `instrumentation-genai/llm-clients/opentelemetry-instrumentation-openai-v2/` for canonical example.
