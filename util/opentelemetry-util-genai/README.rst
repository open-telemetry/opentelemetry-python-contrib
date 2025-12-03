OpenTelemetry Util for GenAI
============================


The GenAI Utils package will include boilerplate and helpers to standardize instrumentation for Generative AI. 
This package will provide APIs and decorators to minimize the work needed to instrument genai libraries, 
while providing standardization for generating both types of otel, "spans and metrics" and "spans, metrics and events"

This package relies on environment variables to configure capturing of message content. 
By default, message content will not be captured.
Set the environment variable `OTEL_SEMCONV_STABILITY_OPT_IN` to `gen_ai_latest_experimental` to enable experimental features.
And set the environment variable `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to one of:
- `NO_CONTENT`: Do not capture message content (default).
- `SPAN_ONLY`: Capture message content in spans only.
- `EVENT_ONLY`: Capture message content in events only.
- `SPAN_AND_EVENT`: Capture message content in both spans and events.

This package provides these span attributes:

- `gen_ai.provider.name`: Str(openai)
- `gen_ai.operation.name`: Str(chat)
- `gen_ai.request.model`: Str(gpt-3.5-turbo)
- `gen_ai.response.finish_reasons`: Slice(["stop"])
- `gen_ai.response.model`: Str(gpt-3.5-turbo-0125)
- `gen_ai.response.id`: Str(chatcmpl-Bz8yrvPnydD9pObv625n2CGBPHS13)
- `gen_ai.usage.input_tokens`: Int(24)
- `gen_ai.usage.output_tokens`: Int(7)
- `gen_ai.input.messages`: Str('[{"role": "Human", "parts": [{"content": "hello world", "type": "text"}]}]')
- `gen_ai.output.messages`: Str('[{"role": "AI", "parts": [{"content": "hello back", "type": "text"}], "finish_reason": "stop"}]')
- `gen_ai.system.instructions`: Str('[{"content": "You are a helpful assistant.", "type": "text"}]') (when system instruction is provided)

When `EVENT_ONLY` or `SPAN_AND_EVENT` mode is enabled and a LoggerProvider is configured, 
the package also emits `gen_ai.client.inference.operation.details` events with structured 
message content (as dictionaries instead of JSON strings).


Installation
------------

::

    pip install opentelemetry-util-genai


Design Document
---------------

The design document for the OpenTelemetry GenAI Utils can be found at: `Design Document <https://docs.google.com/document/d/1w9TbtKjuRX_wymS8DRSwPA03_VhrGlyx65hHAdNik1E/edit?tab=t.qneb4vabc1wc#heading=h.kh4j6stirken>`_

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
