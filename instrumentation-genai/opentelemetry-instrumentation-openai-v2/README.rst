OpenTelemetry OpenAI Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-openai-v2.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-openai-v2/

This library allows tracing LLM requests and logging of messages made by the
`OpenAI Python API library <https://pypi.org/project/openai/>`_. It also captures
the duration of the operations and the number of tokens used as metrics.

Many LLM platforms support the OpenAI SDK. This means systems such as the following are observable with this instrumentation when accessed using it:

.. list-table:: OpenAI Compatible Platforms
   :widths: 40 25
   :header-rows: 1

   * - Name
     - gen_ai.system
   * - `Azure OpenAI <https://github.com/openai/openai-python?tab=readme-ov-file#microsoft-azure-openai>`_
     - ``azure.ai.openai``
   * - `Gemini <https://developers.googleblog.com/en/gemini-is-now-accessible-from-the-openai-library/>`_
     - ``gemini``
   * - `Perplexity <https://docs.perplexity.ai/api-reference/chat-completions>`_
     - ``perplexity``
   * - `xAI <https://x.ai/api>`_ (Compatible with Anthropic)
     - ``xai``
   * - `DeepSeek <https://api-docs.deepseek.com/>`_
     - ``deepseek``
   * - `Groq <https://console.groq.com/docs/openai>`_
     - ``groq``
   * - `MistralAI <https://docs.mistral.ai/api/>`_
     - ``mistral_ai``

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-openai-v2

If you don't have an OpenAI application, yet, try our `examples <examples>`_
which only need a valid OpenAI API key.

Check out `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up OpenAI instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace OpenAI operations including chat completions and embeddings.
You can also optionally capture prompts and completions as log events.

Make sure to configure OpenTelemetry tracing, logging, and events to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    # Chat completion example
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

    # Embeddings example
    embedding_response = client.embeddings.create(
        model="text-embedding-3-small",
        input="Generate vector embeddings for this text"
    )

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function arguments and return values
are not captured by default. To capture message content as log events, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following values:

- ``true`` - Legacy. Used to enable content capturing on ``gen_ai.{role}.message`` and ``gen_ai.choice`` events when
  `latest experimental features <#enabling-the-latest-experimental-features>`_ are *not* enabled.
- ``span_only`` - Used to enable content capturing on *span* attributes when
  `latest experimental features <#enabling-the-latest-experimental-features>`_ are enabled.
- ``event_only`` - Used to enable content capturing on *event* attributes when
  `latest experimental features <#enabling-the-latest-experimental-features>`_ are enabled.
- ``span_and_event`` - Used to enable content capturing on both *span* and *event* attributes when
  `latest experimental features <#enabling-the-latest-experimental-features>`_ are enabled.

Enabling the latest experimental features
***********************************************

To enable the latest experimental features, set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you use
``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append ``,gen_ai_latest_experimental`` to its value.

Without this setting, OpenAI instrumentation aligns with `Semantic Conventions v1.30.0 <https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_
and would not capture additional details introduced in later versions.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    OpenAIInstrumentor().uninstrument()

References
----------
* `OpenTelemetry OpenAI Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation-genai/openai.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_

