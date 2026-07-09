OpenTelemetry Ollama Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-ollama.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-ollama/

This library allows tracing LLM requests and logging of messages made by the
`Ollama Python SDK <https://pypi.org/project/ollama/>`_. It also captures the
duration of the operations and the number of tokens used as metrics.

Telemetry is emitted using the standard OpenTelemetry GenAI semantic conventions
(``gen_ai.*``) through the shared ``opentelemetry-util-genai`` telemetry handler.

.. note::

   This instrumentation currently implements the **latest experimental** GenAI
   semantic conventions path only. You must set
   ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` for full
   functionality, including message-content capture. Without it, message content
   is not captured and the content-mode options below have no effect. A legacy
   (v1.30.0) path is not provided.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-ollama

Usage
-----

This section describes how to set up Ollama instrumentation if you're setting
OpenTelemetry up manually.

.. code-block:: python

    import ollama
    from opentelemetry.instrumentation.ollama import OllamaInstrumentor

    OllamaInstrumentor().instrument()

    # Chat example
    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

    # Generate (text completion) example
    completion = ollama.generate(
        model="llama3.2",
        prompt="Write a short poem on open telemetry.",
    )

    # Embeddings example
    embeddings = ollama.embed(
        model="all-minilm",
        input="Generate vector embeddings for this text",
    )

The instrumentor wraps ``chat``, ``generate``, ``embed`` and ``embeddings`` on
both ``ollama.Client`` and ``ollama.AsyncClient``. The module-level helpers
(``ollama.chat`` etc.) delegate to a shared default client, so they are covered
as well.

Enabling message content
*************************

Message content such as the contents of prompts and completions is not captured
by default. To capture message content, first enable the latest experimental
conventions (see below), then set
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Enabling the latest experimental features
******************************************

Set ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. If you
already use ``OTEL_SEMCONV_STABILITY_OPT_IN`` for other features, append
``,gen_ai_latest_experimental`` to its value.

.. note:: Generative AI semantic conventions are still evolving. The latest
   experimental features will introduce breaking changes in future releases.

Uninstrument
************

.. code-block:: python

    from opentelemetry.instrumentation.ollama import OllamaInstrumentor

    OllamaInstrumentor().instrument()
    # ...
    OllamaInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Ollama Python SDK <https://github.com/ollama/ollama-python>`_
* `OpenTelemetry GenAI Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/gen-ai/>`_
