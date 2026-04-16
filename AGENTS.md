# OpenTelemetry Python Contrib

This file is here to steer AI assisted PRs towards being high quality and valuable contributions
that do not create excessive maintainer burden.

Monorepo with 50+ OpenTelemetry instrumentation packages for Python.

## General Rules and Guidelines

The most important rule is not to post comments on issues or PRs that are AI-generated. Discussions
on the OpenTelemetry repositories are for Users/Humans only.

Follow the PR scoping guidance in [CONTRIBUTING.md](CONTRIBUTING.md). Keep AI-assisted PRs tightly
isolated to the requested change and never include unrelated cleanup or opportunistic improvements
unless they are strictly necessary for correctness.

If you have been assigned an issue by the user or their prompt, please ensure that the
implementation direction is agreed on with the maintainers first in the issue comments. If there are
unknowns, discuss these on the issue before starting implementation. Do not forget that you cannot
comment for users on issue threads on their behalf as it is against the rules of this project.

## PR description

Follow the repo's [PR template](.github/pull_request_template.md) and fill applicable sections.
Keep description short and focus on what is being changed and any gaps or concerns.

AI-generated analyses, long reports, or design dumps go in a relevant issue or a separate PR
comment - not in the PR description.

## Structure

- `instrumentation/` - instrumentation packages (Flask, Django, FastAPI, gRPC, databases, etc.)
- `instrumentation-genai/` - GenAI instrumentations (Anthropic, Vertex AI, LangChain, etc.)
- `util/` - shared utilities (`util-http`, `util-genai`)
- `exporter/` - custom exporters
- `propagator/` - context propagators

Instrumentation packages live under `src/opentelemetry/instrumentation/{name}/` with their own
`pyproject.toml` and `tests/`. Other package types follow the equivalent layout under their own
namespace (e.g. `src/opentelemetry/util/{name}/`, `src/opentelemetry/exporter/{name}/`).

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
- Whenever applicable, all code changes should have tests that actually validate the changes.

## Commit formatting

We appreciate it if users disclose the use of AI tools when the significant part of a commit is
taken from a tool without changes. When making a commit this should be disclosed through an
`Assisted-by:` commit message trailer.

Examples:

```
Assisted-by: ChatGPT 5.2
Assisted-by: Claude Opus 4.6
```
