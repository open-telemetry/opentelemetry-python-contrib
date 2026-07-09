OpenTelemetry Cohere Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-cohere.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-cohere/

This library allows tracing LLM requests and logging of messages made by the
`Cohere Python API library <https://pypi.org/project/cohere/>`_. It also captures
the duration of the operations and the number of tokens used as metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``cohere`` value for ``gen_ai.provider.name``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-cohere

Usage
-----

This section describes how to set up Cohere instrumentation if you're setting OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace Cohere chat and
embedding requests. You can also optionally capture prompts and completions.

Make sure to configure OpenTelemetry tracing, logging, and metrics to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    import cohere
    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    client = cohere.ClientV2()
    # Chat example
    response = client.chat(
        model="command-r",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function arguments and return values
are not captured by default. To capture message content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following values:

- ``span_only`` - Used to enable content capturing on *span* attributes.
- ``event_only`` - Used to enable content capturing on *event* attributes.
- ``span_and_event`` - Used to enable content capturing on both *span* and *event* attributes.

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

Enabling the latest experimental features
***********************************************

This instrumentation emits the latest experimental GenAI semantic conventions.
Enable them by setting the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you use
``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append ``,gen_ai_latest_experimental`` to its value.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    CohereInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Cohere Python API library <https://pypi.org/project/cohere/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
