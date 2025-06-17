OpenTelemetry OpenAI Embeddings API Instrumentation Example
===========================================================

This is an example of how to instrument OpenAI Embeddings API calls with zero code changes,
using ``opentelemetry-instrument``.

When ``main.py`` is run, it exports traces and metrics to an OTLP
compatible endpoint. Traces include details such as the model used,
dimensions of embeddings, and the duration of the embedding request.
Metrics capture token usage and performance data.

Note: ``.env`` file configures additional environment variables:

- ``OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true`` configures OpenTelemetry SDK to export logs and events.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`` configures OpenAI instrumentation to capture content on events.
- ``OTEL_LOGS_EXPORTER=otlp`` to specify exporter type.

Setup
-----

Minimally, update the ``.env`` file with your ``OPENAI_API_KEY``. An
OTLP compatible endpoint should be listening for traces and logs on
http://localhost:4317. If not, update ``OTEL_EXPORTER_OTLP_ENDPOINT`` as well.

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

    dotenv run -- opentelemetry-instrument python main.py

You should see embedding information printed while traces and metrics export to your
configured observability tool.