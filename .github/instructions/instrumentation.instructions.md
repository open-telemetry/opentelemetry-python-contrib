---
applyTo: "{instrumentation,instrumentation-genai}/**"
---

Review rules for PRs touching `instrumentation/**` and `instrumentation-genai/**`. Flag violations
with a link to the rule.

## 0. Reviewer mindset

Review as long-term maintainer.

For new instrumentations, consult upstream library docs and judge:

- Does the library already emit its own telemetry, making this instrumentation redundant?
- Is the library used widely enough to warrant a package in this repo?
- Does it avoid unbounded in-memory accumulation or other side-effects?

For changes to existing instrumentations: prefer back-compat. Break users only for a real reason;
prefer opt-in or additive. Breaking changes need explicit justification in the PR.

## 1. Component ownership & maintenance commitment

- New instrumentations must add an entry under the correct folder in
  [`component_owners.yml`](../component_owners.yml) in the same PR. Contributor must commit to
  long-term maintenance. See
  [Expectations from contributors](../../CONTRIBUTING.md#expectations-from-contributors) and the
  general [instrumentation checklist](../../CONTRIBUTING.md#guideline-for-instrumentations).

## 2. Semantic conventions

- Attribute names must come from the semconv attribute modules, not hardcoded strings. Use the
  module matching the namespace under `opentelemetry.semconv` (e.g. `server_attributes`,
  `error_attributes`, `http_attributes`, `db_attributes`, …).
- For attributes with a well-known value set in semconv, use the generated enum from the same
  modules instead of string literals.
- If a signal is not in semconv, wait until semconv lands.

## 3. Exception handling

- No new `raise` statements in instrumentation/telemetry code.
- When catching library exceptions to record telemetry, re-raise the original exception
  unmodified.

## 4. Tests

- For every public API instrumented, cover sync/async variants when both exist.
- Cover happy path and error scenarios.
- Tests must verify exact attribute names **and value types**, checked against the semconv spec.
- Test against oldest and latest supported library versions via `tests/requirements.{oldest,latest}.txt`
  and `{oldest,latest}` `tox.ini` factors.

See also [AGENTS.md](../../AGENTS.md) for general repo rules.
