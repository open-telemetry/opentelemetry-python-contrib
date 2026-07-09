OpenTelemetry LiteLLM Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-litellm.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-litellm/

This library allows tracing LLM requests and logging of messages made by the
`LiteLLM Python library <https://pypi.org/project/litellm/>`_. It also captures
the duration of the operations and the number of tokens used as metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Because LiteLLM is a router that normalizes many providers to
the OpenAI response shape, ``gen_ai.provider.name`` is derived per call from the
back-end that LiteLLM actually dispatched to (see `Provider resolution`_).

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-litellm

Usage
-----

This section describes how to set up LiteLLM instrumentation if you're setting
OpenTelemetry up manually.

.. code-block:: python

    import litellm
    from opentelemetry.instrumentation.litellm import LiteLLMInstrumentor

    LiteLLMInstrumentor().instrument()

    # Chat completion example
    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

The instrumentation wraps the module-level functions ``litellm.completion`` /
``litellm.acompletion`` (chat) and ``litellm.embedding`` /
``litellm.aembedding`` (embeddings), covering both synchronous and asynchronous
variants as well as streaming responses.

Provider resolution
*******************

``gen_ai.provider.name`` is derived per call from the provider LiteLLM
dispatched to, in order of preference:

1. The response's ``_hidden_params["custom_llm_provider"]``.
2. An explicit ``custom_llm_provider`` request keyword argument.
3. The provider prefix on a ``provider/model`` model string (e.g. ``bedrock``
   in ``bedrock/anthropic.claude-3``).

LiteLLM prefixes that differ from the OTel well-known values are normalized to
the matching ``gen_ai.provider.name`` value (for example ``bedrock`` ->
``aws.bedrock``, ``vertex_ai`` -> ``gcp.vertex_ai``, ``gemini`` ->
``gcp.gemini``, ``mistral`` -> ``mistral_ai``). Unknown providers pass through
unchanged, since ``gen_ai.provider.name`` accepts either a well-known enum value
or an arbitrary string. When the provider cannot be determined (a bare model
whose provider is only known after the response), it falls back to the literal
``"litellm"``.

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` ``TelemetryHandler`` and requires the latest
experimental GenAI semantic conventions. Set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental`` (or append
``,gen_ai_latest_experimental`` to its existing value).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function
arguments and return values are not captured by default. To capture message
content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uninstrument
************

To uninstrument, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.litellm import LiteLLMInstrumentor

    LiteLLMInstrumentor().instrument()
    # ...

    # Uninstrument
    LiteLLMInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `LiteLLM Python library <https://pypi.org/project/litellm/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
