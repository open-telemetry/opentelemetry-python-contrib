OpenTelemetry IBM watsonx.ai Instrumentation
============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-watsonx.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-watsonx/

This library allows tracing LLM requests and logging of messages made by the
`IBM watsonx.ai Python SDK <https://pypi.org/project/ibm-watsonx-ai/>`_. It also
captures the duration of the operations and the number of tokens used as
metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``ibm.watsonx.ai`` value for
``gen_ai.provider.name``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-watsonx

Usage
-----

This section describes how to set up IBM watsonx.ai instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all ``ModelInference`` instances will
automatically trace text generation and chat completions. You can also
optionally capture prompts and completions as span attributes.

Make sure to configure OpenTelemetry tracing, logging, and metrics to capture
all telemetry emitted by the instrumentation.

.. code-block:: python

    from ibm_watsonx_ai.foundation_models import ModelInference
    from opentelemetry.instrumentation.watsonx import WatsonxInstrumentor

    WatsonxInstrumentor().instrument()

    model = ModelInference(
        model_id="google/flan-ul2",
        credentials={"apikey": "...", "url": "https://us-south.ml.cloud.ibm.com"},
        project_id="...",
    )
    response = model.generate(prompt="Write a short poem on open telemetry.")

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the IBM watsonx.ai instrumentation is a no-op** (a
legacy Semantic Conventions v1.30.0 path is not yet provided).

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

    from opentelemetry.instrumentation.watsonx import WatsonxInstrumentor

    WatsonxInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    WatsonxInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `IBM watsonx.ai Python SDK <https://pypi.org/project/ibm-watsonx-ai/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
