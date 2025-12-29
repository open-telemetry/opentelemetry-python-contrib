# Skill: Enhance GenAI Instrumentation

This skill helps add or update instrumentation capabilities for GenAI packages by referencing the OpenLLMetry implementations.

## Usage

```
/enhance-genai <package>
```

Examples:
- `/enhance-genai bedrock` - Add AWS Bedrock instrumentation
- `/enhance-genai cohere` - Add Cohere instrumentation
- `/enhance-genai pinecone` - Add Pinecone vector DB instrumentation

## Trigger

Use this skill when the user asks to:
- "Add instrumentation for [package]"
- "Enhance [package] instrumentation"
- "Port [package] from OpenLLMetry"
- "Update [package] with OpenLLMetry features"
- "Add [package] like the others"

## Available OpenLLMetry Packages

Check `/home/ubuntu/opentelemetry-python-contrib/openllmetry/packages/` for available references:

| Package | Type | Status in instrumentation-genai |
|---------|------|--------------------------------|
| `opentelemetry-instrumentation-anthropic` | LLM | ✅ Implemented |
| `opentelemetry-instrumentation-chromadb` | Vector DB | ✅ Implemented |
| `opentelemetry-instrumentation-google-generativeai` | LLM | Compare with google-genai |
| `opentelemetry-instrumentation-vertexai` | LLM | Compare with existing |
| `opentelemetry-instrumentation-langchain` | Framework | Compare with existing |
| `opentelemetry-instrumentation-openai` | LLM | Compare with openai-v2 |
| `opentelemetry-instrumentation-openai-agents` | Agents | Compare with openai-agents-v2 |
| `opentelemetry-instrumentation-bedrock` | LLM | New - can add |
| `opentelemetry-instrumentation-cohere` | LLM | New - can add |
| `opentelemetry-instrumentation-groq` | LLM | New - can add |
| `opentelemetry-instrumentation-mistralai` | LLM | New - can add |
| `opentelemetry-instrumentation-ollama` | LLM | New - can add |
| `opentelemetry-instrumentation-together` | LLM | New - can add |
| `opentelemetry-instrumentation-replicate` | LLM | New - can add |
| `opentelemetry-instrumentation-pinecone` | Vector DB | New - can add |
| `opentelemetry-instrumentation-qdrant` | Vector DB | New - can add |
| `opentelemetry-instrumentation-milvus` | Vector DB | New - can add |
| `opentelemetry-instrumentation-lancedb` | Vector DB | New - can add |
| `opentelemetry-instrumentation-marqo` | Vector DB | New - can add |
| `opentelemetry-instrumentation-llamaindex` | Framework | New - can add |
| `opentelemetry-instrumentation-haystack` | Framework | New - can add |
| `opentelemetry-instrumentation-crewai` | Agents | New - can add |

## Workflow

### Step 1: Analyze OpenLLMetry Package

Read and understand the OpenLLMetry implementation:

```
openllmetry/packages/opentelemetry-instrumentation-{package}/
├── opentelemetry/instrumentation/{package}/
│   ├── __init__.py      # Main instrumentor
│   ├── utils.py         # Utilities (dont_throw, etc.)
│   └── ...              # Other modules
├── tests/
└── pyproject.toml
```

Key things to identify:
1. **WRAPPED_METHODS**: Which methods are instrumented
2. **Span attributes**: What attributes are captured
3. **Streaming support**: How streaming is handled
4. **Metrics**: What metrics are recorded
5. **Events**: What log events are emitted
6. **Special features**: Caching, tool use, images, etc.

### Step 2: Create/Update Package Structure

Target location: `instrumentation-genai/opentelemetry-instrumentation-{package}/`

Standard structure:
```
src/opentelemetry/instrumentation/{package}/
├── __init__.py      # Instrumentor class with WRAPPED_METHODS
├── version.py       # Version "2.0b0.dev"
├── package.py       # _instruments tuple
├── utils.py         # Utilities (is_content_enabled, dont_throw, etc.)
├── patch.py         # Wrapper functions
├── instruments.py   # Metrics (if applicable)
├── streaming.py     # Streaming support (if applicable)
└── semconv.py       # Local semantic conventions (if needed)
```

### Step 3: Adapt to instrumentation-genai Patterns

Key differences from OpenLLMetry:

| Aspect | OpenLLMetry | instrumentation-genai |
|--------|-------------|----------------------|
| Build system | Poetry | Hatchling |
| Semantic conventions | `opentelemetry-semantic-conventions-ai` | Local `semconv.py` or standard semconv |
| Package structure | Flat | Nested `src/` |
| Version format | `0.x.x` | `2.0b0.dev` |
| License header | Traceloop | OpenTelemetry Authors |
| Dependencies | `opentelemetry-api ^1.38.0` | `opentelemetry-api ~= 1.37` |

### Step 4: Required Files

#### pyproject.toml
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
instruments = [
  "{package} >= X.X.X",
]

[project.entry-points.opentelemetry_instrumentor]
{package} = "opentelemetry.instrumentation.{package}:{Package}Instrumentor"

[tool.hatch.version]
path = "src/opentelemetry/instrumentation/{package}/version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/opentelemetry"]
```

#### version.py
```python
__version__ = "2.0b0.dev"
```

#### package.py
```python
_instruments = ("{package} >= X.X.X",)
```

### Step 5: Implementation Patterns

#### Main Instrumentor (__init__.py)
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

#### Utils (utils.py)
```python
def dont_throw(func):
    """Decorator that prevents exceptions from propagating."""
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

#### Streaming (streaming.py)
For LLM packages with streaming:
```python
class {Package}Stream:
    def __init__(self, stream, span, instruments, ...):
        self._stream = stream
        self._span = span
        ...

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self._stream)
            # Process item, track metrics
            return item
        except StopIteration:
            self._finish()
            raise
```

### Step 6: Documentation

Create `.claude/` documentation file describing the implementation.

Update `.claude/instrumentation-genai-enhancements.md` or create new doc.

### Step 7: Verification

After implementation:
1. Check imports work: `python -c "from opentelemetry.instrumentation.{package} import {Package}Instrumentor"`
2. Run linting: `tox -e ruff`
3. Run tests if available

## Example Command

To enhance a package:
```
/enhance-genai anthropic
/enhance-genai chromadb
/enhance-genai bedrock
```

## Reference Files

Key reference implementations:
- **LLM pattern**: `instrumentation-genai/opentelemetry-instrumentation-anthropic/`
- **Vector DB pattern**: `instrumentation-genai/opentelemetry-instrumentation-chromadb/`
- **Existing enhanced**: `instrumentation-genai/opentelemetry-instrumentation-openai-v2/`
- **OpenLLMetry reference**: `openllmetry/packages/opentelemetry-instrumentation-*/`
