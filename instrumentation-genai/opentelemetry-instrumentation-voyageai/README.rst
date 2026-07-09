OpenTelemetry Voyage AI Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-voyageai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-voyageai/

This library allows tracing embeddings requests made by the
`Voyage AI Python API library <https://pypi.org/project/voyageai/>`_. It also
captures the duration of the operation and the number of input tokens used as
metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``voyageai`` value for ``gen_ai.provider.name`` /
``gen_ai.system`` and the ``embeddings`` operation. Because embedding tokens
are all input tokens, only ``gen_ai.usage.input_tokens`` (and the corresponding
input-token metric) are recorded -- no output-token signals are emitted.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-voyageai

Usage
-----

This section describes how to set up Voyage AI instrumentation if you're setting
OpenTelemetry up manually.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace Voyage AI
embeddings.

Make sure to configure OpenTelemetry tracing and metrics to capture all
telemetry emitted by the instrumentation.

.. code-block:: python

    import voyageai
    from opentelemetry.instrumentation.voyageai import VoyageAIInstrumentor

    VoyageAIInstrumentor().instrument()

    client = voyageai.Client()
    # Embeddings example
    result = client.embed(
        texts=["The capital of France is Paris."],
        model="voyage-3-lite",
        input_type="document",
    )

Enabling the latest experimental features
***********************************************

To enable the latest experimental features, set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you
use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append
``,gen_ai_latest_experimental`` to its value.

Without this setting, Voyage AI instrumentation aligns with
`Semantic Conventions v1.30.0 <https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_
and would not capture additional details introduced in later versions.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.voyageai import VoyageAIInstrumentor

    VoyageAIInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    VoyageAIInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Voyage AI Python API library <https://pypi.org/project/voyageai/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
