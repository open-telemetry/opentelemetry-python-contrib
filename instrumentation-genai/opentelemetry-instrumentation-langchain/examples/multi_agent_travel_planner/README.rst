Multi-Agent Travel Planner Sample
=================================

This example shows how to orchestrate a small team of LangChain agents with
`LangGraph <https://python.langchain.com/docs/langgraph/>`_ while the
OpenTelemetry LangChain instrumentation captures GenAI spans and forwards them
to an OTLP collector.

The graph contains four specialists (coordinator, flights, hotels, activities)
and a final synthesiser node that produces an itinerary.  Each specialist relies
on a simple, deterministic tool so you can run the example without any external
travel APIs while still observing tool spans wired up to the agent calls.

Prerequisites
-------------

* Python 3.10+
* An OpenAI API key with access to ``gpt-4o-mini`` (or set ``OPENAI_MODEL`` to a
  model that is available to your account)
* A running OTLP collector (gRPC on ``localhost:4317`` by default)

Setup
-----

.. code-block:: bash

   cd instrumentation-genai/opentelemetry-instrumentation-langchain/examples/multi_agent_travel_planner
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

   # Copy the sample environment file and update values as needed.
   cp .env.example .env
   source .env

Run the sample
--------------

.. code-block:: bash

   # From this directory, after activating the virtual environment and sourcing
   # your environment variables:
   python main.py

The script prints each agent's contribution followed by the final itinerary.
At the same time it streams OTLP traces.  You should see:

* A root span named ``invoke_agent travel_multi_agent_planner`` that captures
  the overall orchestration, including ``gen_ai.input.messages`` and a preview
  of the final plan.
* LangChain instrumentation spans for each agent's LLM invocation with
  ``gen_ai.provider.name=openai`` and ``service.name`` derived from
  ``OTEL_SERVICE_NAME``.

Tear down
---------

Deactivate the virtual environment when you are done:

.. code-block:: bash

   deactivate
