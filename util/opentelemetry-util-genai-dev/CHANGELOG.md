# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Add a utility to parse the `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable.
  Add `gen_ai_latest_experimental` as a new value to the Sem Conv stability flag ([#3716](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3716)).

### Added

- Generate Spans for LLM invocations
- Helper functions for starting and finishing LLM invocations
