# OpenTelemetry Python Contrib

Monorepo with 50+ OpenTelemetry instrumentation packages for Python.

## Structure

- `instrumentation/` - instrumentation packages (Flask, Django, FastAPI, gRPC, databases, etc.)
- `instrumentation-genai/` - GenAI instrumentations (Anthropic, Vertex AI, LangChain, etc.)
- `util/` - shared utilities (`util-http`, `util-genai`)
- `exporter/` - custom exporters
- `propagator/` - context propagators

Each package lives under `src/opentelemetry/instrumentation/{name}/` with its own `pyproject.toml` and `tests/`.

## Commands

```sh
# Install all packages and dev tools
uv sync --frozen --all-packages

# Lint (runs ruff via pre-commit)
uv run pre-commit run ruff --all-files

# Test a specific package (append -0, -1, etc. for version variants)
uv run tox -e py312-test-instrumentation-flask-0

# Type check
uv run tox -e typecheck
```

## Guidelines

- Each package has its own `pyproject.toml` with version, dependencies, and entry points.
- The monorepo uses `uv` workspaces.
- `tox.ini` defines the test matrix - check it for available test environments.
- Do not add `type: ignore` comments. If a type error arises, solve it properly or write a follow-up plan to address it in another PR.
