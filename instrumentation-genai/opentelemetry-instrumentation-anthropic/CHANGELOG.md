# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Initial implementation of Anthropic instrumentation
  ([#3978](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3978))
- Implement sync `Messages.create` instrumentation with GenAI semantic convention attributes
  ([#4034](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4034))
  - Captures request attributes: `gen_ai.request.model`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.request.top_k`, `gen_ai.request.stop_sequences`
  - Captures response attributes: `gen_ai.response.id`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
  - Error handling with `error.type` attribute
  - Minimum supported anthropic version is 0.16.0 (SDK uses modern `anthropic.resources.messages` module structure introduced in this version)
- Add streaming and async support for Anthropic instrumentation
  ([#4146](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4146))
  - Async support: `AsyncMessages.create()` and `AsyncMessages.stream()` methods
  - Streaming support: `Messages.create(stream=True)` and `Messages.stream()` helper method
  - All streaming responses properly capture telemetry data (response model, response ID, stop reason, token usage)

