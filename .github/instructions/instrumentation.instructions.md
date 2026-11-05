---
applyTo: "{instrumentation,instrumentation-genai}/**"
---

Review rules for PRs touching `instrumentation/**` and `instrumentation-genai/**`. Flag violations
with a link to the rule.

## 0. GenAI instrumentations maintained elsewhere

GenAI instrumentations are developed and released from the
[opentelemetry-python-genai](https://github.com/open-telemetry/opentelemetry-python-genai)
repository. Everything left under `instrumentation-genai/` here is deprecated, receives security
patches only, and will be removed from this repository in the future.

Reject PRs that add features or fix non-security bugs in these packages and point the author to
the `opentelemetry-python-genai` repo. See
[instrumentation-genai/AGENTS.md](../../instrumentation-genai/AGENTS.md).

## 1. Reviewer mindset

Review as long-term maintainer.

For new instrumentations, consult upstream library docs and judge:

- Does the library already emit its own telemetry, making this instrumentation redundant?
- Is the library used widely enough to warrant a package in this repo?
- Does it avoid unbounded in-memory accumulation or other side-effects?

For changes to existing instrumentations: prefer back-compat. Break users only for a real reason;
prefer opt-in or additive. Breaking changes need explicit justification in the PR.

## 2. Component ownership & maintenance commitment

- New instrumentations must add an entry under the correct folder in
  [`component_owners.yml`](../component_owners.yml) in the same PR. Contributor must commit to
  long-term maintenance. See
  [Expectations from contributors](../../CONTRIBUTING.md#expectations-from-contributors) and the
  general [instrumentation checklist](../../CONTRIBUTING.md#guideline-for-instrumentations).

## 3. Semantic conventions

- Attribute names must come from the semconv attribute modules, not hardcoded strings. Use the
  module matching the namespace under `opentelemetry.semconv` (e.g. `server_attributes`,
  `error_attributes`, `http_attributes`, `db_attributes`, …).
- For attributes with a well-known value set in semconv, use the generated enum from the same
  modules instead of string literals.
- If a signal is not in semconv, wait until semconv lands.

## 4. Exception handling

- When catching exceptions from the underlying library to record telemetry, always re-raise the
  original exception unmodified.
- Do not raise **new** exceptions in instrumentation/telemetry code.

## 5. Tests

- For every public API instrumented, cover sync/async variants when both exist.
- Cover happy path and error scenarios.
- Tests must verify exact attribute names **and value types**, checked against the semconv spec.
- Test against oldest and latest supported library versions via `tests/requirements.{oldest,latest}.txt`
  and `{oldest,latest}` `tox.ini` factors.

See also [AGENTS.md](../../AGENTS.md) for general repo rules.
