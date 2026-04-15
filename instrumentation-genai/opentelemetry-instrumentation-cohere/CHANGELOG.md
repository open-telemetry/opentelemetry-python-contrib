# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Initial implementation of Cohere instrumentation
  ([#4418](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4418))
- Implement sync and async `V2Client.chat` instrumentation with GenAI semantic convention attributes
  - Captures request attributes: `gen_ai.request.model`, `gen_ai.request.max_tokens`, `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.request.frequency_penalty`, `gen_ai.request.presence_penalty`, `gen_ai.request.seed`, `gen_ai.request.stop_sequences`
  - Captures response attributes: `gen_ai.response.id`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
  - Error handling with `error.type` attribute
  - Minimum supported cohere version is 5.0.0
