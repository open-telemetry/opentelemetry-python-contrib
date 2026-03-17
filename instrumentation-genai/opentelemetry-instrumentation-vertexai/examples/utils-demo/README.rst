OpenTelemetry GenAI Utils — create_agent Demo
===============================================

This example shows how to combine ``VertexAIInstrumentor`` (automatic
instrumentation of Vertex AI SDK calls) with manual
``TelemetryHandler.create_agent()`` spans from ``opentelemetry-util-genai``
to extend existing instrumentation with agent lifecycle spans.

The demo performs the following steps:

1. **LLM call** — generates content via the ``google-genai`` SDK (API key).
   Vertex AI SDK calls are auto-instrumented by ``VertexAIInstrumentor``.
2. **Local agent creation** — creates a ``LanggraphAgent`` wrapped in a
   ``create_agent`` span.
3. **Deploy to Agent Engine** — deploys the agent to Vertex AI Agent Engine,
   also wrapped in a ``create_agent`` span.
4. **Query the remote agent** — sends a currency exchange query.
5. **Cleanup** — deletes the deployed agent.

Prerequisites
-------------

- A GCP project with the **Vertex AI API** enabled.
- **Application Default Credentials** (ADC) configured:
  ``gcloud auth application-default login``
- A **Google API key** for LLM calls (set as ``GOOGLE_API_KEY``).
- A **GCS staging bucket** for agent deployment:

::

    gsutil mb -p <PROJECT_ID> -l us-central1 -b on gs://<PROJECT_ID>-agent-staging/
    gsutil pap set enforced gs://<PROJECT_ID>-agent-staging/

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

    export GOOGLE_API_KEY="AIza..."
    export GCP_PROJECT="your-project-id"
    python main.py

The deploy step takes 3-5 minutes. You should see two ``create_agent``
spans printed to the console and exported to your OTLP endpoint (one for
local agent creation, one for the deploy), along with the agent's response
to the currency exchange query.

Environment Variables
---------------------

- ``GOOGLE_API_KEY`` — API key for ``google-genai`` SDK LLM calls.
- ``GCP_PROJECT`` — GCP project ID (default: ``gcp-o11yinframon-nprd-81065``).
- ``GCP_LOCATION`` — GCP region (default: ``us-central1``).
- ``GCP_STAGING_BUCKET`` — GCS bucket for agent staging
  (default: ``gs://<GCP_PROJECT>-agent-staging``).
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` — OTLP endpoint
  (default: ``http://localhost:4317``).
