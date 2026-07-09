OpenTelemetry Haystack Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-haystack.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-haystack/

This library allows tracing Haystack pipeline runs made with the
`Haystack (haystack-ai) Python library <https://pypi.org/project/haystack-ai/>`_.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Each pipeline run is mapped to a single GenAI *workflow* span
(``gen_ai.operation.name = invoke_workflow``).

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-haystack

Usage
-----

This section describes how to set up Haystack instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting all pipelines
***************************

When using the instrumentor, all Haystack pipeline runs (both synchronous
``Pipeline.run`` and asynchronous ``AsyncPipeline.run_async``) are
automatically traced as workflow spans.

.. code-block:: python

    from haystack import Pipeline
    from opentelemetry.instrumentation.haystack import HaystackInstrumentor

    HaystackInstrumentor().instrument()

    pipeline = Pipeline()
    # ... add and connect components ...
    result = pipeline.run({"component": {"input": "value"}})

Scope and design decisions
**************************

This instrumentation maps each pipeline run to a single GenAI *workflow* span
by wrapping the pipeline entry points:

- ``haystack.core.pipeline.pipeline.Pipeline.run`` (synchronous)
- ``haystack.core.pipeline.async_pipeline.AsyncPipeline.run_async`` (asynchronous)

It deliberately does **not** wrap the individual generator/embedder components
inside a pipeline. Those components typically delegate to provider SDKs (for
example the ``openai`` package), which are instrumented by their own dedicated
OpenTelemetry instrumentations. Wrapping them here as well would
double-instrument those provider calls, so component-level telemetry is left to
the respective provider instrumentations (install and enable them alongside
this package to get nested spans within the workflow span).

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry through the latest experimental GenAI
semantic conventions. To capture message content (see below) and any future
content-gated attributes, set the environment variable
``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``. Or, if you
use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features, append
``,gen_ai_latest_experimental`` to its value.

The workflow span itself is emitted regardless of this setting; the opt-in
gates the experimental, content-carrying attributes only.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Message content is not captured by default. To capture message content, set
the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uninstrument
************

To uninstrument pipelines, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.haystack import HaystackInstrumentor

    HaystackInstrumentor().instrument()
    # ...

    # Uninstrument all pipelines
    HaystackInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Haystack (haystack-ai) Python library <https://pypi.org/project/haystack-ai/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
