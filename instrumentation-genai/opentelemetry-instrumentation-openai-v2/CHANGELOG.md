# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## Version 2.0b0 (2024-11-05)

- Use generic `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable
  to control if content of prompt, completion, and other messages is captured.
  ([#2947](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2947))

- Update OpenAI instrumentation to Semantic Conventions v1.28.0: add new attributes
  and switch prompts and completions to log-based events.
  ([#2925](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2925))

- Initial OpenAI instrumentation
  ([#2759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2759))