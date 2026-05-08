# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Pass tool definitions from `tools` kwarg to `InferenceInvocation.tool_definitions`
  so `gen_ai.tool.definitions` span attribute is populated on chat completion spans
  ([#4554](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4554))

## Version 2.4b0 (2026-05-01)


- Migrate experimental path from deprecated `LLMInvocation` to `InferenceInvocation`,
  using `handler.start_inference()` and `invocation.stop()`/`invocation.fail()` directly
  ([#4502](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4502))
- Use `create_duration_histogram` and `create_token_histogram` from
  `opentelemetry-util-genai` instead of defining bucket boundaries locally
  ([#4501](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4501))
- Import `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` from
  `opentelemetry.util.genai.environment_variables` instead of re-defining it locally,
  making `opentelemetry-util-genai` the single source of truth for this constant.
  ([#4455](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4455))
- Fix compatibility with wrapt 2.x by using positional arguments in `wrap_function_wrapper()` calls
  ([#4445](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4445))
- Fix `ChoiceBuffer` crash on streaming tool-call deltas with `arguments=None`
  ([#4350](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4350))
- Fix `StreamWrapper` missing `.headers` and other attributes when using `with_raw_response` streaming
  ([#4113](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/4113))
- Add opt-in support for latest experimental semantic conventions (v1.37.0). Set
  `OTEL_SEMCONV_STABILITY_OPT_IN` to `gen_ai_latest_experimental` to enable.
  Add dependency on `opentelemetry-util-genai` pypi package.
  ([#3715](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3715))
- Add wrappers for OpenAI Responses API streams and response stream managers
  ([#4280](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4280))
- Add async wrappers for OpenAI Responses API streams and response stream managers
  ([#4325](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4325))
- Add strongly typed Responses API extractors with validation and content
  extraction improvements
  ([#4337](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4337))
- Add completion hook support.
  ([#4315](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4315))
- Fix `response_format` handling: map `json_object`/`json_schema` to `json` output type.
  ([#4315](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4315))
- Skip attribute values with `openai.Omit` value.
  ([#4315](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4315))
- Default empty string for `gen_ai.request.model` attribute on missing model.
  ([#4494](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4494))

## Version 2.3b0 (2025-12-24)

- Fix `AttributeError` when handling `LegacyAPIResponse` (from `with_raw_response`)
  ([#4017](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4017))
- Add support for chat completions choice count and stop sequences span attributes
  ([#4028](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4028))
- Fix crash with streaming `with_raw_response`
  ([#4033](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4033))
- Bump to 1.30.0 semconv schema: `gen_ai.request.seed` instead of `gen_ai.openai.request.seed`
  ([#4036](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4036))

## Version 2.2b0 (2025-11-25)

- Fix service tier attribute names: use `GEN_AI_OPENAI_REQUEST_SERVICE_TIER` for request
  attributes and `GEN_AI_OPENAI_RESPONSE_SERVICE_TIER` for response attributes.
  ([#3920](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3920))
- Added support for OpenAI embeddings instrumentation
  ([#3461](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3461))
- Record prompt and completion events regardless of span sampling decision.
  ([#3226](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3226))
- Filter out attributes with the value of NotGiven instances
  ([#3760](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3760))
- Migrate off the deprecated events API to use the logs API
  ([#3625](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3628))

## Version 2.1b0 (2025-01-18)

- Coerce openai response_format to semconv format
  ([#3073](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3073))
- Add example to `opentelemetry-instrumentation-openai-v2`
  ([#3006](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3006))
- Support for `AsyncOpenAI/AsyncCompletions` ([#2984](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2984))
- Add metrics ([#3180](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3180))

## Version 2.0b0 (2024-11-08)

- Use generic `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable
  to control if content of prompt, completion, and other messages is captured.
  ([#2947](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2947))

- Update OpenAI instrumentation to Semantic Conventions v1.28.0: add new attributes
  and switch prompts and completions to log-based events.
  ([#2925](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2925))

- Initial OpenAI instrumentation
  ([#2759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2759))
