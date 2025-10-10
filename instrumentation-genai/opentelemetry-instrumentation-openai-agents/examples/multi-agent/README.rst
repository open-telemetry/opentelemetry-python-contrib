OpenTelemetry OpenAI Agents Multi-Agent Example
===============================================

This example coordinates two specialized agents to produce a combined travel
recommendation. The example captures prompts, responses, and tool interactions
for both agents so you can explore multi-span traces in your GenAI telemetry
backend.

Setup
-----

1. Copy `.env.example <.env.example>`_ to `.env` and update ``OPENAI_API_KEY``.
   Adjust the OTLP endpoint variables as needed for your collector.
2. Create a virtual environment and install the dependencies:

   ::

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       pip install -r requirements.txt

Run
---

Launch both agents and examine the spans they generate:

::

    dotenv run -- python main.py

Set ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to ``span_only`` or
``event_only`` to limit capture, or to ``no_content`` to suppress prompts and
responses entirely for this scenario. Leaving it unset records content in both
span attributes and events. Boolean strings such as ``true``/``false`` are also
accepted.
