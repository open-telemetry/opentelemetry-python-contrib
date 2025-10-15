# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Update instrumentation to use the latest semantic convention changes made in https://github.com/open-telemetry/semantic-conventions/pull/2179.
Now only a single event and span (`gen_ai.client.inference.operation.details`) are used to capture prompt and response content. These changes are opt-in,
users will need to set the environment variable OTEL_SEMCONV_STABILITY_OPT_IN to `gen_ai_latest_experimental` to see them ([#3799](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3799)) and ([#3709](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3709)). Update instrumentation to call upload hook.
- Implement uninstrument for `opentelemetry-instrumentation-vertexai`
  ([#3328](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3328))
- VertexAI support for async calling
  ([#3386](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3386))
  - Migrate off the deprecated events API to use the logs API
  ([#3625](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3626))
  - Update `gen_ai_latest_experimental` instrumentation to record files being passed to the model
  ([#3840](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3840)).

## Version 2.0b0 (2025-02-24)

- Added Vertex AI spans for request parameters
  ([#3192](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3192))
- Initial VertexAI instrumentation
  ([#3123](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3123))
- Add server attributes to Vertex AI spans
  ([#3208](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3208))
- VertexAI emit user, system, and assistant events
  ([#3203](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3203))
- Add Vertex gen AI response attributes and `gen_ai.choice` events
  ([#3227](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3227))
- VertexAI stop serializing unset fields into event
  ([#3236](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3236))
- Vertex capture tool requests and responses
  ([#3255](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3255))
