# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version 0.7b0 (2026-02-20)
- Fix bug in how tokens are counted when using the streaming `generateContent` method.  ([#4152](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4152)).
- Add `gen_ai.tool.definitions` attribute to `gen_ai.client.inference.operation.details` log event ([#4142](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4142)).
- Add `gen_ai.tool_definitions` to completion hook ([#4181](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4181))


## Version 0.6b0 (2026-01-27)

- Enable the addition of custom attributes to the `generate_content {model.name}` span via the Context API. ([#3961](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3961)).
- Enable the addition of custom attributes to `gen_ai.client.inference.operation.details` log events ([#4103](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4103)).

## Version 0.5b0 (2025-12-11)

- Ensure log event is written and completion hook is called even when model call results in exception. Put new
log event (` gen_ai.client.inference.operation.details`) behind the flag `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
Ensure same sem conv attributes are on the log and span. Fix an issue where the instrumentation would crash when a pydantic.BaseModel class was passed as the response schema ([#3905](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3905)).
- Add the `GEN_AI_OUTPUT_TYPE` sem conv request attributes to events/spans generated in the stable instrumentation. This was added pre sem conv 1.36 so it should be in the stable instrumentation. Fix a bug in how system instructions were recorded in the `gen_ai.system.message` log event. It will now always be recorded as `{"content" : "text of system instructions"}`. See ([#4011](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4011)).

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
