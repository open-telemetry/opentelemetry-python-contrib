OpenTelemetry Together AI Instrumentation
=========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-together.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-together/

This library allows tracing LLM requests and logging of messages made by the
`Together Python API library <https://pypi.org/project/together/>`_. It also captures
the duration of the operations and the number of tokens used as metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``together`` value for ``gen_ai.provider.name`` /
``gen_ai.system``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-together

Usage
-----

This section describes how to set up Together AI instrumentation if you're setting OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace Together AI chat completions.
You can also optionally capture prompts and completions as log events.

Make sure to configure OpenTelemetry tracing, logging, and events to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    from together import Together
    from opentelemetry.instrumentation.together import TogetherInstrumentor

    TogetherInstrumentor().instrument()

    client = Together()
    # Chat completion example
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
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

To enable the latest experimental features, set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you use
``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append ``,gen_ai_latest_experimental`` to its value.

Without this setting, Together AI instrumentation aligns with `Semantic Conventions v1.30.0 <https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_
and would not capture additional details introduced in later versions.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.together import TogetherInstrumentor

    TogetherInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    TogetherInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Together Python API library <https://pypi.org/project/together/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
