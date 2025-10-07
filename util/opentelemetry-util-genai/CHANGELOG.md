# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- Add jsonlines support to fsspec uploader
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3791](#3791))
- Rename "fsspec_upload" entry point and classes to more generic "upload"
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3798](#3798))
- Record content-type and use canonical paths in fsspec genai uploader
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3795](#3795))
- Make inputs / outputs / system instructions optional params to `on_completion`,
  ([https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3802](#3802)).
  - `opentelemetry-instrumentation-google-genai`: migrate off the deprecated events API to use the logs API
  ([#3625](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3624))


## Version 0.1b0 (2025-09-25)

- Add completion hook to genai utils to implement semconv v1.37.

  Includes a hook implementation using
  [`fsspec`](https://filesystem-spec.readthedocs.io/en/latest/) to support uploading to various
  pluggable backends.

  ([#3780](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3780))
  ([#3752](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3752))
  ([#3759](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3759))
  ([#3763](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3763))
- Add a utility to parse the `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable.
  Add `gen_ai_latest_experimental` as a new value to the Sem Conv stability flag ([#3716](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3716)).
