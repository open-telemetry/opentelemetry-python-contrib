GenAI Utils Demo — Full Agent Lifecycle (Create + Invoke + Metrics)
===================================================================

Combined demo that exercises the full ``TelemetryHandler`` agent lifecycle
on Vertex AI Agent Engine:

1. **Create** a local LanggraphAgent (``create_agent`` span)
2. **Deploy** it to Vertex AI Agent Engine (``create_agent`` span, ~4 min)
3. **Invoke** the deployed agent (``invoke_agent`` span with auto-instrumented
   ``chat`` child span)
4. **Cleanup** — delete the deployed agent

Combines ``VertexAIInstrumentor`` (auto-instrumentation) with manual
``TelemetryHandler`` spans from ``opentelemetry-util-genai``.

Exports traces, metrics, and log-based events to a local OTLP collector.

Prerequisites
-------------

- GCP project with Vertex AI API enabled
- ``gcloud auth application-default login`` (ADC credentials)
- OTLP-compatible collector on ``http://localhost:4317``

Setup
-----

::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install "python-dotenv[cli]"
    pip install -r requirements.txt

    # Install local editable packages
    pip install -e ../../../../util/opentelemetry-util-genai/ -e ../../

Run
---

::

    export GCP_PROJECT="your-project-id"
    dotenv run -- python main.py

Expected Telemetry
------------------

**Spans:**

- ``create_agent Currency Exchange Agent`` — local agent creation (~ms)
- ``create_agent Currency Exchange Agent`` — deploy to Agent Engine (~4 min)
- ``invoke_agent Currency Exchange Agent`` — query the deployed agent (~4s)
- ``chat gemini-2.5-flash`` — auto-instrumented child of invoke_agent

**Metrics:**

- ``gen_ai.client.operation.duration`` — histogram for each operation
- ``gen_ai.client.token.usage`` — input/output token counts

**Events:**

- ``gen_ai.invoke_agent`` log events with message content (when
  ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` is set)
