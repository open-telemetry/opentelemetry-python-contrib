# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Change `InferenceInvocation` init params to only accept base params
- Pass in `attributes` on invocation `_start` so samplers have access to attributes.
  ([#4538](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4538))
- Apply attribute for sampling on instantiation of all invocation types.
  ([#4553](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4553))
- Minor code cleanup and changes in preparation of moving google's GenAI instrumentation
  library to use this util library ([#4556](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4556))

## Version 0.4b0 (2026-05-01)

- Add `AgentInvocation` type with `invoke_agent` span lifecycle
  ([#4274](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4274))
- Add metrics support for EmbeddingInvocation
  ([#4377](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4377))
- Add support for workflow in genAI utils handler.
  ([#4366](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4366))
- Enrich ToolCall type, breaking change: usage of ToolCall class renamed to ToolCallRequest
  ([#4218](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4218))
- Add EmbeddingInvocation span lifecycle support
  ([#4219](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4219))
- Populate schema_url on metrics
  ([#4320](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4320))
- Add workflow invocation type to genAI utils
  ([#4310](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4310))
- Check if upload works at startup in initializer of the `UploadCompletionHook`, instead
of repeatedly failing on every upload ([#4390](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4390)).
- Refactor public API: add factory methods (`start_inference`, `start_embedding`, `start_tool`, `start_workflow`) and invocation-owned lifecycle (`invocation.stop()` / `invocation.fail(exc)`); rename `LLMInvocation` → `InferenceInvocation` and `ToolCall` → `ToolInvocation`. Existing usages remain fully functional via deprecated aliases.
  ([#4391](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4391))
- `TelemetryHandler` now accepts a `completion_hook` parameter and calls it after each LLM invocation, passing inputs, outputs, the active span, and the log record. Content capture is enabled automatically when a real hook is configured.
  ([#4315](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4315))
- Add metrics to ToolInvocations ([#4443](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4443))
- Wrap completion hooks loaded via `load_completion_hook` so exceptions raised by
  `on_completion` are logged and swallowed instead of propagating to instrumentation
  call sites.

## Version 0.3b0 (2026-02-20)

- Add `gen_ai.tool_definitions` to completion hook ([#4181](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4181))
- Add support for emitting inference events and enrich message types. ([#3994](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3994))
- Add support for `server.address`, `server.port` on all signals and additional metric-only attributes
  ([#4069](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4069))
- Log error when `fsspec` fails to be imported instead of silently failing ([#4037](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4037)).
- Minor change to check LRU cache in Completion Hook before acquiring semaphore/thread ([#3907](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3907)).
- Add environment variable for genai upload hook queue size
  ([#3943](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3943))
- Add more Semconv attributes to LLMInvocation spans.
  ([#3862](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3862))
- Limit the upload hook thread pool to 64 workers
  ([#3944](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3944))
- Add metrics to LLMInvocation traces
  ([#3891](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3891))
- Add parent class genAI invocation
  ([#3889](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3889))

## Version 0.2b0 (2025-10-14)

- Add jsonlines support to fsspec uploader
  ([#3791](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3791))
- Rename "fsspec_upload" entry point and classes to more generic "upload"
  ([#3798](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3798))
- Record content-type and use canonical paths in fsspec genai uploader
  ([#3795](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3795))
- Make inputs / outputs / system instructions optional params to `on_completion`,
  ([#3802](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3802)).
- Use a SHA256 hash of the system instructions as it's upload filename, and check
  if the file exists before re-uploading it, ([#3814](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3814)).

## Version 0.1b0 (2025-09-25)

- Add completion hook to genai utils to implement semconv v1.37.

  Includes a hook implementation using
  [`fsspec`](https://filesystem-spec.readthedocs.io/en/latest/) to support uploading to various
  pluggable backends.

  ([#3780](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3780))
  ([#3752](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3752))
  ([#3759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3759))
  ([#3763](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3763))

- Add a utility to parse the `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable.
  Add `gen_ai_latest_experimental` as a new value to the Sem Conv stability flag ([#3716](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3716)).

### Added

- Generate Spans for LLM invocations
- Helper functions for starting and finishing LLM invocations
