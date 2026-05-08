OpenTelemetry Util for GenAI
============================

The GenAI Utils package provides boilerplate and helpers to standardize instrumentation for Generative AI.
It offers APIs to minimize the work needed to instrument GenAI libraries,
while providing standardization for generating spans, metrics, and events.


Key Components
--------------

- ``TelemetryHandler`` -- manages LLM invocation lifecycles (spans, metrics, events)
- ``InferenceInvocation`` and message types (``Text``, ``Reasoning``, ``Blob``, etc.) -- structured data model for GenAI interactions
- ``CompletionHook`` -- protocol for uploading content to external storage (built-in ``fsspec`` support)
- Metrics -- ``gen_ai.client.operation.duration`` and ``gen_ai.client.token.usage`` histograms


Usage
-----

See the module docstring in ``opentelemetry.util.genai.handler`` for usage examples,
including context manager and manual lifecycle patterns.


Environment Variables
---------------------

This package relies on environment variables to configure capturing of message content.
By default, message content will not be captured.
Set the environment variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental`` to enable experimental features.
Set the environment variable ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of:

- ``NO_CONTENT``: Do not capture message content (default).
- ``SPAN_ONLY``: Capture message content in spans only.
- ``EVENT_ONLY``: Capture message content in events only.
- ``SPAN_AND_EVENT``: Capture message content in both spans and events.

To control event emission, you can optionally set ``OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT`` to ``true`` or ``false`` (case-insensitive).
This variable controls whether to emit ``gen_ai.client.inference.operation.details`` events.
If not explicitly set, the default value is automatically determined by ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT``:

- When ``NO_CONTENT`` or ``SPAN_ONLY`` is set: defaults to ``false``
- When ``EVENT_ONLY`` or ``SPAN_AND_EVENT`` is set: defaults to ``true``

If explicitly set, the user's value takes precedence over the default.

When ``EVENT_ONLY`` or ``SPAN_AND_EVENT`` mode is enabled and a LoggerProvider is configured,
the package also emits ``gen_ai.client.inference.operation.details`` events with structured
message content (as dictionaries instead of JSON strings). Note that when using ``EVENT_ONLY``
or ``SPAN_AND_EVENT``, the ``OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT`` environment variable defaults
to ``true``, so events will be emitted automatically unless explicitly set to ``false``.

Completion Hook / Upload
^^^^^^^^^^^^^^^^^^^^^^^^

- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``: Name of the completion hook entry point to load (e.g. ``upload``).
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH``: An ``fsspec``-compatible URI/path for uploading prompts and completions
  (e.g. ``/path/to/prompts`` or ``gs://my_bucket``). Required when using the ``upload`` hook.
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT``: Format for uploaded data -- ``json`` (default) or ``jsonl``.
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE``: Maximum number of concurrent uploads to queue (default: ``20``).


Span Attributes
---------------

This package sets the following span attributes on LLM invocations:

**Common attributes:**

- ``gen_ai.operation.name``: Str(chat)
- ``gen_ai.provider.name``: Str(openai)
- ``gen_ai.request.model``: Str(gpt-4o)
- ``server.address``: Str(api.openai.com)
- ``server.port``: Int(443)

**Response attributes:**

- ``gen_ai.response.finish_reasons``: Slice(["stop"])
- ``gen_ai.response.model``: Str(gpt-4o-2024-05-13)
- ``gen_ai.response.id``: Str(chatcmpl-Bz8yrvPnydD9pObv625n2CGBPHS13)
- ``gen_ai.usage.input_tokens``: Int(24)
- ``gen_ai.usage.output_tokens``: Int(7)

**Request parameter attributes (when provided):**

- ``gen_ai.request.temperature``: Float(0.7)
- ``gen_ai.request.top_p``: Float(1.0)
- ``gen_ai.request.frequency_penalty``: Float(0.0)
- ``gen_ai.request.presence_penalty``: Float(0.0)
- ``gen_ai.request.max_tokens``: Int(1024)
- ``gen_ai.request.stop_sequences``: Slice(["\\n"])
- ``gen_ai.request.seed``: Int(42)

**Content attributes (sensitive, requires content capturing enabled):**

- ``gen_ai.input.messages``: Str('[{"role": "user", "parts": [{"content": "hello world", "type": "text"}]}]')
- ``gen_ai.output.messages``: Str('[{"role": "assistant", "parts": [{"content": "hello back", "type": "text"}], "finish_reason": "stop"}]')
- ``gen_ai.system_instructions``: Str('[{"content": "You are a helpful assistant.", "type": "text"}]')

**Error attributes:**

- ``error.type``: Str(TimeoutError)

Embedding Span Attributes
-------------------------

This package also supports embedding invocation spans via the ``embedding`` context manager.
For embedding invocations, the following attributes are set:

**Common attributes:**

- ``gen_ai.operation.name``: Str(embeddings)
- ``gen_ai.provider.name``: Str(openai)
- ``server.address``: Str(api.openai.com)
- ``server.port``: Int(443)

**Request attributes:**

- ``gen_ai.request.model``: Str(text-embedding-3-small)
- ``gen_ai.embeddings.dimension.count``: Int(1536)
- ``gen_ai.request.encoding_formats``: Slice(["float"])

**Response attributes:**

- ``gen_ai.response.model``: Str(text-embedding-3-small)
- ``gen_ai.usage.input_tokens``: Int(24)


Installation
------------

::

    pip install opentelemetry-util-genai

For upload support (requires ``fsspec``)::

    pip install opentelemetry-util-genai[upload]


Design Document
---------------

The design document for the OpenTelemetry GenAI Utils can be found at: `Design Document <https://docs.google.com/document/d/1LzNGylxot5zaIV1goOJZ2mz3LI0weFu1SgaMnyDv7gg/edit?usp=sharing>`_

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
