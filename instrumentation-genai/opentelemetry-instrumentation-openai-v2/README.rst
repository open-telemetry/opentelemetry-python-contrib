OpenTelemetry OpenAI Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-openai-v2.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-openai-v2/

This library allows tracing LLM requests and logging of messages made by the
`OpenAI Python API library <https://pypi.org/project/openai/>`_. It also captures
the duration of the operations and the number of tokens used as metrics.


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

When using the instrumentor, all clients will automatically trace OpenAI chat completion operations.
You can also optionally capture prompts and completions as log events.

Make sure to configure OpenTelemetry tracing, logging, and events to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function arguments and return values
are not captured by default. To capture message content as log events, set the environment variable
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to `true`.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    OpenAIInstrumentor().uninstrument()

Bucket Boundaries
-----------------

This section describes the explicit bucket boundaries for metrics such as token usage and operation duration, and guides users to create Views to implement them according to the semantic conventions.

The bucket boundaries are defined as follows:

- For `gen_ai.client.token.usage`: [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]
- For `gen_ai.client.operation.duration`: [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]

To implement these bucket boundaries, you can create Views in your OpenTelemetry SDK setup. Here is an example:

.. code-block:: python

    from opentelemetry.sdk.metrics import MeterProvider, View
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics.aggregation import ExplicitBucketHistogramAggregation

    views = [
        View(
            instrument_name="gen_ai.client.token.usage",
            aggregation=ExplicitBucketHistogramAggregation([1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]),
        ),
        View(
            instrument_name="gen_ai.client.operation.duration",
            aggregation=ExplicitBucketHistogramAggregation([0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]),
        ),
    ]

    metric_exporter = OTLPMetricExporter(endpoint="http://localhost:4317")
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    provider = MeterProvider(
        metric_readers=[metric_reader],
        views=views
    )

    from opentelemetry.sdk.metrics import set_meter_provider
    set_meter_provider(provider)

For more details, refer to the `OpenTelemetry GenAI Metrics documentation <https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/>`_.

References
----------
* `OpenTelemetry OpenAI Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/openai/openai.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_

