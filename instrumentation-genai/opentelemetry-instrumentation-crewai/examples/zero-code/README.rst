OpenTelemetry CrewAI Zero-Code Instrumentation Example
========================================================

This is an example of how to instrument CrewAI with zero code changes,
using ``opentelemetry-instrument``.

When `main.py <main.py>`_ is run, it builds a two-agent crew (a researcher
with a word-count tool, and a writer who summarizes the researcher's
output) and exports the trace to an OTLP compatible endpoint, without a
single line of OpenTelemetry code in ``main.py`` itself -- instrumentation
is discovered and wired up automatically at process startup via
``opentelemetry-instrument``.

Note: `.env.example <.env.example>`_ configures additional environment
variables:

- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only`` captures prompt/response content on span attributes.
- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` enables latest experimental features -- required for the message content above to actually appear.

Setup
-----

Copy `.env.example <.env.example>`_ to ``.env`` and update it with your
``OPENAI_API_KEY``. An OTLP compatible endpoint should be listening for
traces on http://localhost:4317. If not, update
``OTEL_EXPORTER_OTLP_ENDPOINT`` as well.

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

You should see a two-sentence summary printed, while the trace exports to
your configured observability tool.
