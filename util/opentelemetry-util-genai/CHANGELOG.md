# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Enrich ToolCall type ([#4218](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4218))
- Add `gen_ai.tool_definitions` to completion hook ([#4181](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4181))
- Add support for emitting inference events and enrich message types. ([#3994](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3994))
- Add support for `server.address`, `server.port` on all signals and additional metric-only attributes
  ([#4069](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4069))
- Log error when `fsspec` fails to be imported instead of silently failing ([#4037](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4037)).
- Minor change to check LRU cache in Completion Hook before acquiring semaphore/thread ([#3907](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3907)).
- Add environment variable for genai upload hook queue size
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3943](#3943))
- Add more Semconv attributes to LLMInvocation spans.
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3862](#3862))
- Limit the upload hook thread pool to 64 workers
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3944](#3944))
- Add metrics to LLMInvocation traces
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3891](#3891))
- Add parent class genAI invocation
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3889](#3889))

## Version 0.2b0 (2025-10-14)

- Add jsonlines support to fsspec uploader
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3791](#3791))
- Rename "fsspec_upload" entry point and classes to more generic "upload"
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3798](#3798))
- Record content-type and use canonical paths in fsspec genai uploader
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3795](#3795))
- Make inputs / outputs / system instructions optional params to `on_completion`,
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3802](#3802)).
  - Use a SHA256 hash of the system instructions as it's upload filename, and check
  if the file exists before re-uploading it, ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3814](#3814)).


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
