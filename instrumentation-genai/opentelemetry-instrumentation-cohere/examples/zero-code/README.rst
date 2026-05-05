OpenTelemetry Cohere Zero-Code Instrumentation Example
======================================================

This is an example of how to use OpenTelemetry's automatic instrumentation
(zero-code) capabilities with the Cohere SDK.

The `opentelemetry-instrument` CLI automatically instruments your Python
application without requiring code changes. Once chat completions support is
added in a follow-up PR, running `main.py <main.py>`_ with the CLI will
export traces and logs to an OTLP compatible endpoint.

Note: `.env <.env>`_ file configures additional environment variables:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` is included for
  consistency with other GenAI instrumentations, but it currently has no
  effect for Cohere. Chat completions support has not yet been implemented.

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

Run the example with zero-code instrumentation like this:

::

    dotenv run -- opentelemetry-instrument python main.py

This runs `main.py` under automatic instrumentation. Once chat completions
support is added in a follow-up PR, Cohere SDK calls will produce traces and
logs exported to your configured observability tool without code changes.

Learn More
----------

See the `OpenTelemetry Python automatic instrumentation docs
<https://opentelemetry.io/docs/languages/python/automatic/>`_ for more
information about zero-code instrumentation.
