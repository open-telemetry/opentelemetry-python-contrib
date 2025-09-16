OpenTelemetry LangChain Instrumentation Example
==============================================

This is an example of how to instrument LangChain calls when configuring
OpenTelemetry SDK and Instrumentations manually.

When :code:`main.py <main.py>` is run, it exports traces (and optionally logs)
to an OTLP-compatible endpoint. Traces include details such as the chain name,
LLM usage, token usage, and durations for each operation.

Environment variables:

- ``OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT=true`` can be used
  to capture full prompt/response content.

Setup
-----

1. **Update** the :code:`.env <.env>` file with any environment variables you
   need (e.g., your OpenAI key, or :code:`OTEL_EXPORTER_OTLP_ENDPOINT` if not
   using the default http://localhost:4317).
2. Set up a virtual environment:

   .. code-block:: console

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       pip install -r requirements.txt

3. **(Optional)** Install a development version of the new instrumentation:

   .. code-block:: console

       # E.g., from a local path or a git repo
       pip install -e /path/to/opentelemetry-python-contrib/instrumentation-genai/opentelemetry-instrumentation-langchain
Run
---

Run the example like this:

.. code-block:: console

    dotenv run -- opentelemetry-instrument python main.py

You should see an example chain output while traces are exported to your
configured observability tool.