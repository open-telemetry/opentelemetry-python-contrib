---
applyTo: "instrumentation-genai/**"
---

Review rules for PRs touching `instrumentation-genai/**`. Flag violations with a link to the rule.

These rules are additive to
[`instrumentation.instructions.md`](instrumentation.instructions.md), which applies to all
instrumentation packages.

## 1. Scope of `instrumentation-genai/`

Only for:

- Generative AI inference providers,
- Agentic frameworks,
- Libraries directly supporting the above (e.g., MCP, GenAI protocols).

Database clients (including vector DBs used outside a GenAI-specific client) and CLI libs belong
in `instrumentation/`, not here.

## 2. GenAI component ownership

See [`CONTRIBUTING.md#guideline-for-genai-instrumentations`](../../CONTRIBUTING.md#guideline-for-genai-instrumentations)
for GenAI-specific maintenance expectations on top of the general
[instrumentation checklist](../../CONTRIBUTING.md#guideline-for-instrumentations).

## 3. Telemetry and configuration via `opentelemetry-util-genai`

- Spans, logs, metrics, and events must go through `opentelemetry-util-genai`. Direct use of
  `Tracer`, `Meter`, `Logger`, or event APIs is not allowed.
- Content capture, hooks, and other cross-cutting configuration are owned by the util.
  Instrumentations must not introduce their own env vars, settings, or hook interfaces.
- Message content, prompts, and tool call arguments must only be set through the util's content
  capture path — never as unconditional span/log attributes.
- Adding attributes to invocations produced by the util is fine.
- If a capability is missing in `opentelemetry-util-genai`, land it in the util first.

## 4. GenAI semantic conventions

- Attributes, spans, events, and metrics must match the
  [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai).
- `gen_ai.*` attribute names must come from
  `opentelemetry.semconv._incubating.attributes.gen_ai_attributes`.
- For attributes with a well-known value set, use the generated enum from the same module
  (e.g. `GenAiOutputTypeValues` for `gen_ai.output.type`) instead of string literals.

## 5. Tests

- Use recorded VCR cassettes for provider calls. No live-key-only tests; skipping on missing key
  is not acceptable.
- Cover streaming and non-streaming variants when both exist.
- For error scenarios, at minimum include: provider error / endpoint unavailable, stream
  interrupted by network, stream closed early by the caller.

## 6. Examples

New instrumentations must ship a minimal example under the package's `examples/`, with both a
`manual/` and a `zero-code/` (auto-instrumentation) variant.

## 7. PR description

- Cover which part of the GenAI semconv the change implements or follows (when applicable) and
  how instrumentations should consume it.

See also [AGENTS.md](../../AGENTS.md) for general repo rules.
