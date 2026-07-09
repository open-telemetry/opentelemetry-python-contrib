OpenTelemetry Replicate Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-replicate.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-replicate/

This library allows tracing LLM requests and logging of messages made by the
`Replicate Python API library <https://pypi.org/project/replicate/>`_. It also
captures the duration of the operations as a metric.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Replicate predictions map to the ``text_completion`` operation,
and the ``replicate`` value is used for ``gen_ai.provider.name``.

.. note::
    Replicate responses do not report token usage, so token-usage attributes
    (``gen_ai.usage.*``) and the token-usage metric are not emitted.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-replicate

Usage
-----

This section describes how to set up Replicate instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace Replicate
runs and streams. You can also optionally capture prompts and completions.

Make sure to configure OpenTelemetry tracing, logging, and events to capture all
telemetry emitted by the instrumentation.

.. code-block:: python

    import replicate
    from opentelemetry.instrumentation.replicate import ReplicateInstrumentor

    ReplicateInstrumentor().instrument()

    output = replicate.run(
        "meta/meta-llama-3-8b-instruct",
        input={"prompt": "Write a short poem on open telemetry."},
    )

Enabling message content
*************************

Message content such as the contents of the prompt and completion are not
captured by default. To capture message content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - Capture content on *span* attributes.
- ``event_only`` - Capture content on *event* attributes.
- ``span_and_event`` - Capture content on both *span* and *event* attributes.

Enabling the latest experimental features
***********************************************

This instrumentation only emits telemetry on the latest experimental GenAI
semantic conventions. Set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you
use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append
``,gen_ai_latest_experimental`` to its value.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.replicate import ReplicateInstrumentor

    ReplicateInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    ReplicateInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Replicate Python API library <https://pypi.org/project/replicate/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
