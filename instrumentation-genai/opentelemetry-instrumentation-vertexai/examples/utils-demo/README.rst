OpenTelemetry GenAI Utils — invoke_agent Demo
================================================

This example shows how to combine ``VertexAIInstrumentor`` (automatic
instrumentation of Vertex AI SDK calls) with manual
``TelemetryHandler.agent()`` spans from ``opentelemetry-util-genai``
to extend existing instrumentation with agent invocation lifecycle spans.

The ``generate_content`` call is made inside the ``invoke_agent`` context,
so the auto-instrumented LLM span appears as a child of the ``invoke_agent``
parent span — all within the same trace.

Sample Trace
------------

::

    Trace ID: 0xe71e16deb2ecd162e3f4fc67c240818b
    |
    +-- invoke_agent Currency Exchange Agent          [4.16s, root span]
        |   gen_ai.operation.name:        invoke_agent
        |   gen_ai.agent.name:            Currency Exchange Agent
        |   gen_ai.agent.description:     Currency exchange agent demo
        |   gen_ai.provider.name:         gcp_vertex_ai
        |   gen_ai.request.model:         gemini-2.5-flash
        |   gen_ai.response.finish_reasons: ["stop"]
        |   gen_ai.usage.input_tokens:    12
        |   gen_ai.usage.output_tokens:   87
        |   server.address:               us-central1-aiplatform.googleapis.com
        |   scope:                        opentelemetry.util.genai.handler
        |
        +-- chat gemini-2.5-flash                     [4.12s, child span]
            gen_ai.operation.name:        chat
            gen_ai.system:                vertex_ai
            gen_ai.request.model:         gemini-2.5-flash
            gen_ai.response.model:        gemini-2.5-flash
            gen_ai.response.finish_reasons: ["stop"]
            gen_ai.usage.input_tokens:    12
            gen_ai.usage.output_tokens:   87
            server.address:               us-central1-aiplatform.googleapis.com
            server.port:                  443
            scope:                        opentelemetry.instrumentation.vertexai

Prerequisites
-------------

- A GCP project with the **Vertex AI API** enabled.
- **Application Default Credentials** (ADC) configured:
  ``gcloud auth application-default login``

Setup
-----

An OTLP compatible endpoint should be listening for traces and logs on
http://localhost:4317. If not, update ``OTEL_EXPORTER_OTLP_ENDPOINT``.

Set up a virtual environment:

::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install -e ../../../../util/opentelemetry-util-genai/

Run
---

::

    export GCP_PROJECT="your-project-id"
    python main.py

You should see an ``invoke_agent`` span wrapping a ``chat`` child span,
both printed to the console and exported to your OTLP endpoint.

Environment Variables
---------------------

- ``GCP_PROJECT`` — GCP project ID (default: ``gcp-o11yinframon-nprd-81065``).
- ``GCP_LOCATION`` — GCP region (default: ``us-central1``).
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` — OTLP endpoint
  (default: ``http://localhost:4317``).
