# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

Create an initial version of Open Telemetry instrumentation for github.com/googleapis/python-genai.

This version adds support for instrumenting `Client.models.generate_content` but does not yet support
instrumentation for streaming and async use cases.

This version supports some of the `gen_ai.request.*` span attributes but does not cover all of the
GenAI semantic conventions for spans that are applicable just yet.
