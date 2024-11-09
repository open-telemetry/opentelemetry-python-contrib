# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Added a wrapper for `AsyncCompletions.create` inside `src/opentelemetry/instrumentation/openai_v2/__init__.py` to instrument async chat completions
- Created a new patch function for async chat completions
- Abstracted handling span exceptions into it's own function as it was getting used in multiple places
- Adjusted `StreamWrapper` to include async methods for supporting async streaming
- Added Tests using `pytest-asyncio` fixtures

## Version 2.0b0 (2024-11-08)

- Use generic `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable
  to control if content of prompt, completion, and other messages is captured.
  ([#2947](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2947))

- Update OpenAI instrumentation to Semantic Conventions v1.28.0: add new attributes
  and switch prompts and completions to log-based events.
  ([#2925](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2925))

- Initial OpenAI instrumentation
  ([#2759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2759))