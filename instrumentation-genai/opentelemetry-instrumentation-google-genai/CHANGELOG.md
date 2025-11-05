# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Minor change to check LRU cache in Completion Hook before acquiring semaphore/thread ([#3907](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3907)).

## Version 0.4b0 (2025-10-16)

- Implement the new semantic convention changes made in https://github.com/open-telemetry/semantic-conventions/pull/2179.
A single event (`gen_ai.client.inference.operation.details`) is used to capture Chat History. This is opt-in,
an environment variable OTEL_SEMCONV_STABILITY_OPT_IN needs to be set to `gen_ai_latest_experimental` to see them ([#3386](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3386))
- Support CompletionHook for upload to cloud storage. 

## Version 0.3b0 (2025-07-08)

- Add automatic instrumentation to tool call functions ([#3446](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3446))

## Version 0.2b0 (2025-04-28)

- Add more request configuration options to the span attributes ([#3374](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3374))
- Restructure tests to keep in line with repository conventions ([#3344](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3344))

- Fix [bug](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3416) where
span attribute `gen_ai.response.finish_reasons` is empty ([#3417](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3417))

## Version 0.1b0 (2025-03-05)

- Add support for async and streaming.
  ([#3298](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3298))

Create an initial version of Open Telemetry instrumentation for github.com/googleapis/python-genai.
([#3256](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3256)) 