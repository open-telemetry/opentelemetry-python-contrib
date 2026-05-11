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

- One logical change per PR. Do not bundle multiple fixes, refactors, or features into the same
  PR - split them up so each can be reviewed and reverted independently.
- Run the linter and the relevant tests locally and make sure they pass. See [Commands](#commands).

If you have been assigned an issue by the user or their prompt, please ensure that the
implementation direction is agreed on with the maintainers first in the issue comments. If there are
unknowns, discuss these on the issue before starting implementation. Do not forget that you cannot
comment for users on issue or pull request threads on their behalf as it is against the rules of this project.

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
- When a file uses `from __future__ import annotations`, do not quote type annotations just to
  avoid forward references. Keep quotes only for expressions still evaluated at runtime, such as
  `typing.cast(...)`, unless the referenced type is imported at runtime.
- Whenever applicable, all code changes should have tests that actually validate the changes.

## Instrumentation rules

Apply to packages under `instrumentation/` and `instrumentation-genai/`.

### Exception handling

- When catching exceptions from the underlying library to record telemetry, always re-raise the
  original exception unmodified.
- Do not raise new exceptions in instrumentation/telemetry code.

### Semantic conventions

- Use the semconv attribute and metrics modules under `opentelemetry.semconv` — do not hardcode
  attribute or metric name strings.
- For attributes with a well-known value set, use the generated enum from the same module instead
  of string literals.

### Tests

- For every public API instrumented, cover sync/async variants when both exist.
- Cover happy path and error scenarios.
- Tests must verify exact attribute names **and value types**, checked against the semconv spec.
- Test against oldest and latest supported library versions via `tests/requirements.{oldest,latest}.txt`
  and `{oldest,latest}` `tox.ini` factors.

The parallel PR-review rules live in
[`.github/instructions/instrumentation.instructions.md`](.github/instructions/instrumentation.instructions.md)
and should be kept in sync with this section.

## Commit formatting

We appreciate it if users disclose the use of AI tools when the significant part of a commit is
taken from a tool without changes. When making a commit this should be disclosed through an
`Assisted-by:` commit message trailer.

Examples:

```
Assisted-by: ChatGPT 5.2
Assisted-by: Claude Opus 4.6
```
