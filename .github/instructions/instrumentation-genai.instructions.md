---
applyTo: "instrumentation-genai/**"
---

Review rules for PRs touching `instrumentation-genai/**`.

GenAI instrumentations are no longer developed in this repository. They live in
[opentelemetry-python-genai](https://github.com/open-telemetry/opentelemetry-python-genai),
which is where new instrumentations, features, and bug fixes go. Everything left under
`instrumentation-genai/` is deprecated, receives security patches only, and will be removed from
this repository in the future.

Reject PRs that add new instrumentations here, add features, or fix non-security bugs, and point
the author to the `opentelemetry-python-genai` repo. See
[instrumentation-genai/AGENTS.md](../../instrumentation-genai/AGENTS.md).
