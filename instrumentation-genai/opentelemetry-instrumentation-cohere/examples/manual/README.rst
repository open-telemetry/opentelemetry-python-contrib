OpenTelemetry Cohere Instrumentation Example
=============================================

This is an example of how to instrument Cohere calls when configuring
OpenTelemetry SDK and Instrumentations manually.

When chat completions support is added in a follow-up PR, `main.py <main.py>`_
will export traces and logs to an OTLP compatible endpoint. For now the
instrumentor is a no-op scaffold.

Note: `.env <.env>`_ file configures additional environment variables:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` is the setting
  that will control whether Cohere instrumentation captures prompt and
  completion contents on events, but it currently has no effect because
  chat completions support has not yet been added.

Setup
-----

An OTLP compatible endpoint should be listening for traces and logs on
http://localhost:4317. If not, update "OTEL_EXPORTER_OTLP_ENDPOINT" as well.

Next, set up a virtual environment like this:

::

    python3 -m venv .venv
    source .venv/bin/activate
    pip install "python-dotenv[cli]"
    pip install -r requirements.txt

You will also need a Cohere API key. Set it as an environment variable:

::

    export CO_API_KEY=your_api_key_here

Run
---

Run the example like this:

::

    dotenv run -- python main.py

At the moment, this example runs the placeholder scaffold in ``main.py``.
Once chat completions support is added, Cohere SDK calls will produce traces
and logs exported to your configured observability tool.
