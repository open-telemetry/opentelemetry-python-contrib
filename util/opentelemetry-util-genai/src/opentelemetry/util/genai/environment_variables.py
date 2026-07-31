# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)

OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT = "OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT

Controls whether to emit gen_ai.client.inference.operation.details events.
Must be one of ``true`` or ``false`` (case-insensitive).
Defaults to ``false``.
"""

OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK = (
    "OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK
"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH

An :func:`fsspec.open` compatible URI/path for uploading prompts and responses. Can be a local
path like ``/path/to/prompts`` or a cloud storage URI such as ``gs://my_bucket``. For more
information, see

* `Instantiate a file-system
  <https://filesystem-spec.readthedocs.io/en/latest/usage.html#instantiate-a-file-system>`_ for supported values and how to
  install support for additional backend implementations.
* `Configuration
  <https://filesystem-spec.readthedocs.io/en/latest/features.html#configuration>`_ for
  configuring a backend with environment variables.
"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT

The format to use when uploading prompt and response data. Must be one of ``json`` or
``jsonl``. Defaults to ``json``.
"""

OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE = (
    "OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE"
)
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE

The maximum number of concurrent uploads to queue. New uploads will be dropped if the queue is
full. Defaults to 20.
"""
