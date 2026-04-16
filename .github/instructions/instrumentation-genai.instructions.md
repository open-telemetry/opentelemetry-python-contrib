---
applyTo: "instrumentation-genai/**"
---

Review rules for PRs touching `instrumentation-genai/**`. Flag violations with a link to the rule.

## 0. Reviewer mindset

Review as long-term maintainer.

For new instrumentations, consult upstream library docs and judge:

- Does the library already emit its own telemetry, making this instrumentation redundant?
- Is the library used widely enough to warrant a package in this repo?
- Does it avoid unbounded in-memory accumulation or other side-effects?
- Does the library raise exceptions that would reach user code through our wrapping?

For changes to existing instrumentations: prefer back-compat. Break users only for a real reason;
prefer opt-in or additive. Breaking changes need explicit justification in the PR.

## 1. Scope of `instrumentation-genai/`

Only for:

- Generative AI inference providers,
- Agentic frameworks,
- Libraries directly supporting the above (e.g., MCP, GenAI protocols).

Database clients (including vector DBs used outside a GenAI-specific client) and CLI libs belong
in `instrumentation/`, not here.

## 2. Component ownership & maintenance commitment

- New instrumentations must add an entry under the correct folder in
  [`component_owners.yml`](../component_owners.yml) in the same PR. Contributor must commit to
  long-term maintenance. See
  [Expectations from contributors](../../CONTRIBUTING.md#expectations-from-contributors),
  [Guideline for GenAI instrumentations](../../CONTRIBUTING.md#guideline-for-genai-instrumentations),
  and the general [instrumentation checklist](../../CONTRIBUTING.md#guideline-for-instrumentations).

## 3. Telemetry and configuration via `opentelemetry-util-genai`

- Spans, logs, metrics, and events must go through `opentelemetry-util-genai`. Direct use of
  `Tracer`, `Meter`, `Logger`, or event APIs is not allowed.
- Content capture, hooks, and other cross-cutting configuration are owned by the util.
  Instrumentations must not introduce their own env vars, settings, or hook interfaces.
- Message content, prompts, and tool call arguments must only be set through the util's content
  capture path — never as unconditional span/log attributes.
- Adding attributes to invocations produced by the util is fine.
- If a capability is missing in `opentelemetry-util-genai`, land it in the util first.

## 4. Semantic conventions

- Attributes, spans, events, and metrics must match the
  [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai).
- If a signal is not in semconv, wait until semconv lands.
- Attribute names must come from the semconv attribute modules, not hardcoded strings:
  - `gen_ai.*`: `opentelemetry.semconv._incubating.attributes.gen_ai_attributes`
  - `server.*`: `opentelemetry.semconv.attributes.server_attributes`
  - `error.*`: `opentelemetry.semconv.attributes.error_attributes`
  - other namespaces: corresponding module under `opentelemetry.semconv`
- For attributes with a well-known value set in semconv, use the generated enum from the same
  modules (e.g. `GenAiOutputTypeValues` for `gen_ai.output.type`) instead of string literals.

## 5. Exception handling

- No `raise` statements in instrumentation/telemetry code. Validation belongs in tests and
  callers.
- When catching library exceptions to record telemetry, re-raise the original exception
  unmodified.

## 6. Tests

- Use recorded VCR cassettes for provider calls. No live-key-only tests; skipping on missing key
  is not acceptable.
- For every public API touched, cover sync/async and streaming/non-streaming variants when both
  exist.
- Cover happy path and error scenarios, at minimum: provider error / endpoint unavailable, stream
  interrupted by network, stream closed early by the caller.
- Tests must verify exact attribute names **and value types**, checked against the semconv spec.
- Test against oldest and latest supported library versions via `tests/requirements.{oldest,latest}.txt`
  and `{oldest,latest}` `tox.ini` factors (see existing GenAI packages).

## 7. Examples

New instrumentations must ship a minimal example under the package's `examples/`, with both a
`manual/` and a `zero-code/` (auto-instrumentation) variant.

## 8. PR description

- Cover which part of the GenAI semconv the change implements or follows (when applicable) and
  how instrumentations should consume it.

See also [AGENTS.md](../../AGENTS.md) for general repo rules.
