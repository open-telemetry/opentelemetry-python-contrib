OpenTelemetry OpenAI Agents Zero-Code Instrumentation Example
=============================================================

This example shows how to capture telemetry from OpenAI Agents without
changing your application code by using ``opentelemetry-instrument``.

When `main.py <main.py>`_ is executed, spans describing the agent workflow are
exported to the configured OTLP endpoint. The spans include details such as the
operation name, tool usage, and token consumption (when available).

Setup
-----

1. Copy `.env.example <.env.example>`_ to `.env` and update it with your real
   ``OPENAI_API_KEY``. Adjust the
   OTLP endpoint settings if your collector is not reachable via
   ``http://localhost:4317``.
2. Create a virtual environment and install the dependencies:

   ::

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       uv pip install -r requirements.txt --prerelease=allow

Run
---

Execute the sample via ``opentelemetry-instrument`` so the OpenAI Agents
instrumentation is activated automatically:

::

    dotenv run -- opentelemetry-instrument python main.py

Ensure ``OPENAI_API_KEY`` is set in your shell or `.env`; the OpenAI client raises ``OpenAIError`` if the key is missing.

Because ``main.py`` invokes ``load_dotenv``, running ``python main.py`` directly
also works when the required environment variables are already exported.

You should see the agent response printed to the console while spans export to
your observability backend.
