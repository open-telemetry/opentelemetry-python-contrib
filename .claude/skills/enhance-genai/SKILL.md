---
name: enhance-genai-instrumentation
description: Add or update OpenTelemetry instrumentation for GenAI packages by porting from OpenLLMetry implementations. Use when asked to add instrumentation for LLM providers (Bedrock, Cohere, Groq, Mistral, Ollama, Together, Replicate), vector databases (Pinecone, Qdrant, Milvus, LanceDB, Marqo), or frameworks (LlamaIndex, Haystack, CrewAI). Triggers on requests like "add instrumentation for [package]", "port [package] from OpenLLMetry", or "enhance [package] instrumentation".
---

# Enhance GenAI Instrumentation

Port OpenTelemetry instrumentation from OpenLLMetry to instrumentation-genai packages.

## Reference Locations

- **OpenLLMetry source**: `/home/ubuntu/opentelemetry-python-contrib/openllmetry/packages/opentelemetry-instrumentation-{package}/`
- **Target location**: `instrumentation-genai/opentelemetry-instrumentation-{package}/`
- **LLM reference**: `instrumentation-genai/opentelemetry-instrumentation-anthropic/`
- **Vector DB reference**: `instrumentation-genai/opentelemetry-instrumentation-chromadb/`

## Workflow

### 1. Analyze OpenLLMetry Package

Read the source implementation and identify:
- `WRAPPED_METHODS` - which methods are instrumented
- Span attributes captured
- Streaming support approach
- Metrics and events emitted
- Special features (caching, tool use, images)

### 2. Create Package Structure

```
src/opentelemetry/instrumentation/{package}/
├── __init__.py      # Instrumentor with WRAPPED_METHODS
├── version.py       # Version "2.0b0.dev"
├── package.py       # _instruments tuple
├── utils.py         # dont_throw, is_content_enabled
├── patch.py         # Wrapper functions
├── instruments.py   # Metrics (if applicable)
├── streaming.py     # Streaming support (if applicable)
└── semconv.py       # Local semantic conventions (if needed)
```

### 3. Key Adaptations from OpenLLMetry

| Aspect | OpenLLMetry | instrumentation-genai |
|--------|-------------|----------------------|
| Build system | Poetry | Hatchling |
| Semantic conventions | `opentelemetry-semantic-conventions-ai` | Local `semconv.py` |
| Package structure | Flat | Nested `src/` |
| Version | `0.x.x` | `2.0b0.dev` |
| License header | Traceloop | OpenTelemetry Authors |
| Dependencies | `opentelemetry-api ^1.38.0` | `opentelemetry-api ~= 1.37` |

### 4. Required pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "opentelemetry-instrumentation-{package}"
dynamic = ["version"]
description = "OpenTelemetry {Package} instrumentation"
readme = "README.rst"
license = "Apache-2.0"
requires-python = ">=3.9"
dependencies = [
  "opentelemetry-api ~= 1.37",
  "opentelemetry-instrumentation ~= 0.58b0",
  "opentelemetry-semantic-conventions ~= 0.58b0",
  "wrapt >= 1.0.0, < 2.0.0",
]

[project.optional-dependencies]
instruments = ["{package} >= X.X.X"]

[project.entry-points.opentelemetry_instrumentor]
{package} = "opentelemetry.instrumentation.{package}:{Package}Instrumentor"

[tool.hatch.version]
path = "src/opentelemetry/instrumentation/{package}/version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/opentelemetry"]
```

### 5. Implementation Patterns

#### Main Instrumentor

```python
from wrapt import wrap_function_wrapper
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap

WRAPPED_METHODS = [
    {"package": "...", "object": "...", "method": "...", "wrapper": "..."},
]

class {Package}Instrumentor(BaseInstrumentor):
    def _instrument(self, **kwargs):
        tracer = get_tracer(...)
        for method_info in WRAPPED_METHODS:
            wrap_function_wrapper(...)

    def _uninstrument(self, **kwargs):
        for method_info in WRAPPED_METHODS:
            unwrap(...)
```

#### Utils

```python
def dont_throw(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.debug("Instrumentation error: %s", e)
    return wrapper

def is_content_enabled():
    return os.environ.get(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
    ).lower() == "true"
```

#### Streaming (for LLM packages)

```python
class {Package}Stream:
    def __init__(self, stream, span, instruments, ...):
        self._stream = stream
        self._span = span

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self._stream)
            return item
        except StopIteration:
            self._finish()
            raise
```

### 6. Verification

```bash
# Check imports
python -c "from opentelemetry.instrumentation.{package} import {Package}Instrumentor"

# Run linting
tox -e ruff

# Run tests
tox -e py3{version}-test-instrumentation-{package}
```

## Available Packages

### Can Add (New)

| Package | Type |
|---------|------|
| bedrock | LLM |
| cohere | LLM |
| groq | LLM |
| mistralai | LLM |
| ollama | LLM |
| together | LLM |
| replicate | LLM |
| pinecone | Vector DB |
| qdrant | Vector DB |
| milvus | Vector DB |
| lancedb | Vector DB |
| marqo | Vector DB |
| llamaindex | Framework |
| haystack | Framework |
| crewai | Agents |

### Compare/Update (Existing)

| Package | Notes |
|---------|-------|
| google-generativeai | Compare with google-genai |
| vertexai | Compare with existing |
| langchain | Compare with existing |
| openai | Compare with openai-v2 |
| openai-agents | Compare with openai-agents-v2 |