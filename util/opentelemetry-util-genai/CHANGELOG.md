# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Repurpose the `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable when GEN AI stability mode is set to `gen_ai_latest_experimental`,
to take on an enum (`NO_CONTENT/SPAN_ONLY/EVENT_ONLY/SPAN_AND_EVENT`) instead of a boolean. Add a utility function to help parse this environment variable.

### Added

- Generate Spans for LLM invocations
- Generate Metrics for LLM invocations
- Helper functions for starting and finishing LLM invocations
