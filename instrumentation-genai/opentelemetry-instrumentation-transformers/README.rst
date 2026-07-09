OpenTelemetry HuggingFace Transformers Instrumentation
======================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-transformers.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-transformers/

This library allows tracing local text-generation inference performed with the
`HuggingFace transformers <https://pypi.org/project/transformers/>`_ library
and logging of the prompts and completions. It also captures the duration of
the operation as a metric.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Because there is no ``GenAiProviderNameValues`` member for
HuggingFace or generic local inference, the ``huggingface`` literal is used for
``gen_ai.provider.name``.

.. note::
   This instruments *local* inference: the model runs in-process, with no
   network call and no hosted provider. A local pipeline exposes no token usage
   and no finish reason, so ``gen_ai.usage.*`` and
   ``gen_ai.response.finish_reasons`` are not emitted.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-transformers

Usage
-----

This section describes how to set up transformers instrumentation if you're
setting OpenTelemetry up manually.

When using the instrumentor, all local text-generation pipelines will
automatically be traced. You can also optionally capture prompts and
completions.

Make sure to configure OpenTelemetry tracing, logging, and metrics to capture
all telemetry emitted by the instrumentation.

.. code-block:: python

    from transformers import pipeline
    from opentelemetry.instrumentation.transformers import (
        TransformersInstrumentor,
    )

    TransformersInstrumentor().instrument()

    generator = pipeline("text-generation", model="gpt2")
    result = generator("Write a short poem on open telemetry.")

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the transformers instrumentation is a no-op** (a legacy
Semantic Conventions v1.30.0 path is not yet provided).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Message content such as the contents of the prompt and completion are not
captured by default. To capture message content, set the environment variable
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

To uninstrument, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.transformers import (
        TransformersInstrumentor,
    )

    TransformersInstrumentor().instrument()
    # ...

    # Uninstrument
    TransformersInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `HuggingFace transformers <https://pypi.org/project/transformers/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
