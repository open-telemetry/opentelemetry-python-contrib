OpenTelemetry OpenAI Agents Handoff Example
==========================================

This example shows how the OpenTelemetry OpenAI Agents instrumentation captures
spans in a small multi-agent workflow. Three agents collaborate: a primary
concierge, a concise assistant with a random-number tool, and a Spanish
specialist reached through a handoff. Running the sample produces
``invoke_agent`` spans for each agent as well as an ``execute_tool`` span for
the random-number function.

Setup
-----

1. Copy `.env.example <.env.example>`_ to `.env` and populate it with your real
   ``OPENAI_API_KEY``. Adjust the OTLP exporter settings if your collector does
   not listen on ``http://localhost:4317``.
2. Create a virtual environment and install the dependencies:

   ::

       python3 -m venv .venv
       source .venv/bin/activate
       pip install "python-dotenv[cli]"
       pip install -r requirements.txt

Run
---

Execute the workflow with ``dotenv`` so the environment variables from ``.env``
are loaded automatically:

::

    dotenv run -- python main.py

The script emits a short transcript to stdout while spans stream to the OTLP
endpoint defined in your environment. You should see multiple
``invoke_agent`` spans (one per agent) and an ``execute_tool`` span for the
random-number helper triggered during the run.
