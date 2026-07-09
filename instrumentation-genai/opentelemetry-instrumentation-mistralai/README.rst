OpenTelemetry Mistral AI Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-mistralai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-mistralai/

This library allows tracing LLM requests and logging of messages made by the
`Mistral AI Python API library <https://pypi.org/project/mistralai/>`_. It also
captures the duration of the operations and the number of tokens used as
metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``mistral_ai`` value for ``gen_ai.provider.name`` /
``gen_ai.system``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-mistralai

Usage
-----

This section describes how to set up Mistral AI instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace Mistral AI
chat completions and embeddings. You can also optionally capture prompts and
completions as log events.

Make sure to configure OpenTelemetry tracing, logging, and metrics to capture
all telemetry emitted by the instrumentation.

.. code-block:: python

    from mistralai import Mistral
    from opentelemetry.instrumentation.mistralai import MistralAiInstrumentor

    MistralAiInstrumentor().instrument()

    client = Mistral(api_key="...")
    # Chat completion example
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the Mistral AI instrumentation is a no-op** (a legacy
Semantic Conventions v1.30.0 path is not yet provided).

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

Uploading prompts and completions
*********************************

To enable the built-in upload hook, set:

- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload``
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` to an ``fsspec``-compatible URI/path
  (e.g. ``/path/to/prompts`` or ``gs://my_bucket``).

Install the ``upload`` extra to pull in ``fsspec``::

    pip install opentelemetry-util-genai[upload]

See the `opentelemetry-util-genai
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for additional options.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.mistralai import MistralAiInstrumentor

    MistralAiInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    MistralAiInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Mistral AI Python API library <https://pypi.org/project/mistralai/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
