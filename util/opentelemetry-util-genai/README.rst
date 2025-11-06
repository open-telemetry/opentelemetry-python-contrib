OpenTelemetry Util for GenAI
============================


The GenAI Utils package will include boilerplate and helpers to standardize instrumentation for Generative AI. 
This package will provide APIs and decorators to minimize the work needed to instrument genai libraries, 
while providing standardization for generating both types of otel, "spans and metrics" and "spans, metrics and events"

This package relies on environment variables to configure capturing of message content. 
By default, message content will not be captured.
Set the environment variable `OTEL_SEMCONV_STABILITY_OPT_IN` to `gen_ai_latest_experimental` to enable experimental features.
And set the environment variable `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to `SPAN_ONLY` or `SPAN_AND_EVENT` to capture message content in spans.

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
