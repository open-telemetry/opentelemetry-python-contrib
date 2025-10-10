OpenTelemetry OpenAI Agents Content Capture Example
===================================================

This example highlights how to customize OpenAI Agents instrumentation to
capture prompts, responses, and tool payloads. By setting
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=event_only`` the sample
records message content as span events without duplicating it on span
attributes. Use ``span_and_event`` (default) or ``span_only`` for alternative
capture modes, or ``no_content`` to disable capture entirely. Boolean strings
such as ``true``/``false`` are also accepted.

Setup
-----

1. Copy `.env.example <.env.example>`_ to `.env` and update ``OPENAI_API_KEY``.
   Adjust the OTLP endpoint variables if you export somewhere other than
   ``http://localhost:4317``.
2. Create a virtual environment and install the dependencies:

   ::

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       pip install -r requirements.txt

Run
---

Execute the sample and inspect the exported telemetry to see prompts, tool
arguments, and responses attached as span events:

::

    dotenv run -- python main.py

Set the ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` environment
variable to the capture mode you want (``span_and_event`` by default, or
``span_only``/``event_only``/``no_content``) before running the sample.
