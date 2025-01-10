OpenTelemetry OpenAI Instrumentation Example
============================================

This is an example of how to instrument OpenAI calls when configuring OpenTelemetry SDK and Instrumentations manually for metrics.

When `main.py <main.py>`_ is run, it exports metrics to an OTLP compatible endpoint. Metrics include details such as token usage and operation duration, with specific bucket boundaries for each metric.

The bucket boundaries are defined as follows:

- For `gen_ai.client.token.usage`: [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]
- For `gen_ai.client.operation.duration`: [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]

These are documented in the `OpenTelemetry GenAI Metrics documentation <https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/>`_.

Setup
-----

Minimally, update the `.env <.env>`_ file with your "OPENAI_API_KEY". An OTLP compatible endpoint should be listening for metrics on http://localhost:4317. If not, update "OTEL_EXPORTER_OTLP_ENDPOINT" as well.

Next, set up a virtual environment like this:

::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install "python-dotenv[cli]"
    pip install -r requirements.txt

Run
---

Run the example like this:

::

    dotenv run -- python main.py

You should see metrics being exported to your configured observability tool, with the specified bucket boundaries for token usage and operation duration.
