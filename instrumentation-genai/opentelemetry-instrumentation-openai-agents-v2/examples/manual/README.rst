OpenTelemetry OpenAI Agents Instrumentation Example
===================================================

This example demonstrates how to manually configure the OpenTelemetry SDK
alongside the OpenAI Agents instrumentation.

Running `main.py <main.py>`_ produces spans for the end-to-end agent run,
including tool invocations and model generations. Spans are exported through
OTLP/gRPC to the endpoint configured in the environment.

Setup
-----

1. Copy `.env.example <.env.example>`_ to `.env` and update it with your real
   ``OPENAI_API_KEY``. If your
   OTLP collector is not reachable via ``http://localhost:4317``, adjust the
   endpoint variables as needed.
2. Create a virtual environment and install the dependencies:

   ::

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       uv pip install -r requirements.txt --prerelease=allow

Run
---

Execute the sample with ``dotenv`` so the environment variables from ``.env``
are applied:

::

    dotenv run -- python main.py

Ensure ``OPENAI_API_KEY`` is present in your environment (or ``.env`` file); the OpenAI client raises ``OpenAIError`` if the key is missing.

The script automatically loads environment variables from ``.env`` so running
``python main.py`` directly also works if the shell already has the required
values exported.

You should see the agent response printed to the console while spans export to
your configured observability backend.
