OpenTelemetry Claude Agent SDK Zero-Code Instrumentation Example
================================================================

This is an example of how to instrument Claude Agent SDK calls with zero
code changes, using ``opentelemetry-instrument``.

Based on the `claude-agent-sdk-python agents example
<https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/agents.py>`_,
this example defines two custom agents — a **code reviewer** and a
**documentation writer** — using ``AgentDefinition``, then runs queries
against them via the ``query()`` API. When `main.py <main.py>`_ is run with
the CLI, it exports traces and logs to an OTLP compatible endpoint. Traces
capture each agent turn, tool invocations, and the duration of the
interaction.

Note: `.env <.env>`_ file configures additional environment variables:

- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`` configures
  Claude Agent SDK instrumentation to capture prompt and completion contents
  on events.
- ``OTEL_LOGS_EXPORTER=otlp`` to specify exporter type.

Setup
-----

Minimally, update the `.env <.env>`_ file with your ``ANTHROPIC_API_KEY``. An
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

Run the example with zero-code instrumentation like this:

::

    dotenv run -- opentelemetry-instrument python main.py

You should see the code reviewer and documentation writer agents respond in
the console while traces and logs export to your configured observability tool.
No changes to ``main.py`` were required!

Learn More
----------

See the `OpenTelemetry Python automatic instrumentation docs
<https://opentelemetry.io/docs/languages/python/automatic/>`_ for more
information about zero-code instrumentation.
