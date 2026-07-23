OpenTelemetry CrewAI Instrumentation Example
=============================================

This is an example of how to instrument CrewAI when configuring the
OpenTelemetry SDK and this instrumentation manually.

When `main.py <main.py>`_ is run, it builds a two-agent crew (a researcher
with a word-count tool, and a writer who summarizes the researcher's
output) and exports traces to an OTLP compatible endpoint. The trace
includes one ``invoke_workflow`` span for the whole run, one
``invoke_agent`` span per agent, and ``chat``/``execute_tool`` spans
underneath. The writer's ``invoke_agent`` span carries a **link** back to
the researcher's, representing the handoff between them.

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

    dotenv run -- python main.py

You should see a two-sentence summary printed, while the trace exports to
your configured observability tool.
