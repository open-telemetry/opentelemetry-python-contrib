# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

OpenTelemetry Python Contrib is a monorepo containing 50+ auto-instrumentation libraries for OpenTelemetry in Python. It includes instrumentations for popular libraries (Flask, Django, requests, boto3, Redis, etc.), GenAI instrumentations (OpenAI, Anthropic, VertexAI), exporters, propagators, and resource detectors.

## Build and Development Commands

### Setup
```bash
pip install tox tox-uv      # Install tox with uv support
uv sync                      # Create .venv with all dependencies (alternative)
pre-commit install           # Install pre-commit hooks (recommended)
```

### Running Tests
```bash
# Run all tests (slow - runs across all packages and Python versions)
tox

# Run tests for a specific instrumentation
tox -e py312-test-instrumentation-requests

# Fast re-run using existing tox environment (skip dependency install)
.tox/py312-test-instrumentation-requests/bin/pytest instrumentation/opentelemetry-instrumentation-requests

# Run benchmarks
tox -f benchmark
```

### Linting and Code Quality
```bash
tox -e ruff                  # Run ruff linter and formatter
tox -e lint-some-package     # Lint a specific package
tox -e precommit             # Run all pre-commit checks
tox -e pyright               # Type checking (strict mode on select packages)
tox -e spellcheck            # Spellcheck
```

### Documentation
```bash
tox -e docs                  # Build documentation
```

### Code Generation
```bash
tox -e generate              # Regenerate bootstrap and other generated files
tox -e generate-workflows    # Regenerate CI workflows after tox.ini changes
python scripts/generate_instrumentation_bootstrap.py  # After adding new instrumentation
```

### Testing Against Different Core Repo Versions
```bash
CORE_REPO_SHA=<commit-hash> tox  # Test against specific commit
```

## Architecture

### Package Structure
- `instrumentation/` - Main instrumentation packages (50+)
- `instrumentation-genai/` - GenAI-specific instrumentations (OpenAI, Anthropic, VertexAI, etc.)
- `opentelemetry-instrumentation/` - Base instrumentation framework with `BaseInstrumentor`
- `exporter/` - Exporters (Prometheus remote-write, RichConsole)
- `propagator/` - Context propagators (AWS X-Ray, OT Trace)
- `resource/` - Resource detectors (Azure, Container ID)
- `util/` - Shared utilities (opentelemetry-util-http, opentelemetry-util-genai)

### Standard Instrumentation Package Layout
```
instrumentation/opentelemetry-instrumentation-{library}/
├── src/opentelemetry/instrumentation/{library}/
│   ├── __init__.py      # Main instrumentor class (extends BaseInstrumentor)
│   ├── version.py       # Version (dynamically read by hatchling)
│   └── package.py       # _instruments dependency definitions
├── tests/
├── pyproject.toml       # Entry points, dependencies, instruments list
└── test-requirements.txt
```

### Key Dependencies
- Packages depend on `opentelemetry-api ~= 1.12` from the core repo
- Core repo packages (api, sdk, semantic-conventions, test-utils) are sourced from `https://github.com/open-telemetry/opentelemetry-python` main branch

### Build Order
Packages must be built in dependency order (defined in `eachdist.ini`):
1. `opentelemetry-instrumentation` (base)
2. `util/opentelemetry-util-http`
3. `instrumentation/opentelemetry-instrumentation-wsgi`
4. `instrumentation/opentelemetry-instrumentation-dbapi`
5. `instrumentation/opentelemetry-instrumentation-asgi`
6. Other instrumentations...

## Code Style

- **Line length**: 79 characters
- **Python version**: 3.9+ minimum
- **Docstrings**: Google style
- **Formatter/Linter**: Ruff (configured in pyproject.toml)
- **Type checking**: Pyright strict mode (progressively enabled)

## Adding New Instrumentation

1. Create package in `instrumentation/opentelemetry-instrumentation-{name}/`
2. Extend from `BaseInstrumentor` class
3. Add entry point in `pyproject.toml`:
   ```toml
   [project.entry-points.opentelemetry_instrumentor]
   library_name = "opentelemetry.instrumentation.library:LibraryInstrumentor"
   ```
4. Run `python scripts/generate_instrumentation_bootstrap.py`
5. Add test environment to `tox.ini`
6. Run `tox -e generate-workflows`
7. Add doc entry in `docs/instrumentation/{name}/{name}.rst`

### Required Instrumentation Features
- Follow semantic conventions (prefer STABLE status)
- Support auto-instrumentation via entry points
- Implement `suppress_instrumentation` functionality
- HTTP instrumentations: `exclude_urls`, `url_filter`, request/response hooks
- Use `is_recording()` optimization on non-sampled spans
- Isolate sync and async tests (use `IsolatedAsyncioTestCase` for async)

## Updating Instrumentation Package Versions

1. Update `pyproject.toml`: modify `instruments` in `[project.optional-dependencies]`
2. Update `package.py`: modify `_instruments` variable
3. Run `tox -e generate` at repo root
4. If adding new version tests: add test-requirements.txt and update tox.ini

## Version Management

- **Stable packages**: version 1.40.0.dev
- **Pre-release packages**: version 0.61b0.dev
- GenAI instrumentations and some AWS/Azure packages have separate release cycles (excluded from main release)
