# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## Version 0.2b0 (2025-04-25)

- Add more request configuration options to the span attributes ([#3374](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3374))
- Restructure tests to keep in line with repository conventions ([#3344](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3344))

- Fix [bug](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3416) where
span attribute `gen_ai.response.finish_reasons` is empty ([#3417](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3417))

## Version 0.1b0 (2025-03-05)

- Add support for async and streaming.
  ([#3298](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3298))

Create an initial version of Open Telemetry instrumentation for github.com/googleapis/python-genai.
([#3256](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3256)) 