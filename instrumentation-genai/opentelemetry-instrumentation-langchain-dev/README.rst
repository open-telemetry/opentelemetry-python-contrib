OpenTelemetry LangChain Instrumentation (Alpha)
=============================================

This package provides OpenTelemetry instrumentation for LangChain LLM/chat
workflows. It now relies solely on ``opentelemetry-util-genai`` (the earlier
``opentelemetry-genai-sdk`` toggle and related environment switch have been removed).

Status: Alpha (APIs and produced telemetry are subject to change).

Features
--------
* Automatic spans for LangChain ChatOpenAI (and compatible) invocations.
* Metrics for LLM latency and token usage (when available from the provider).
* (Optional) message content capture (disabled by default) for spans and logs.
* Tool (function) definitions recorded as request attributes.

Installation
------------
Install from source (monorepo layout example)::

    pip install -e opentelemetry-instrumentation-langchain-alpha/

This will pull in required OpenTelemetry core + ``opentelemetry-util-genai``.

Quick Start
-----------

.. code:: python

    from opentelemetry.instrumentation.langchain import LangChainInstrumentor
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    # (Optionally) configure providers/exporters before instrumentation
    LangChainInstrumentor().instrument()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="What is the capital of France?"),
    ]
    response = llm.invoke(messages)
    print(response.content)

Environment Variables
---------------------

Message content (prompt + completion) is NOT collected unless explicitly enabled:

``OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT``
  Set to ``true`` (case-insensitive) to record message text in spans/logs.

For finer-grained content handling controlled by util-genai you may also use:

``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT``
  (See ``opentelemetry-util-genai`` docs) Values like ``SPAN_ONLY`` etc.

Removed / Deprecated
--------------------
* The legacy ``opentelemetry-genai-sdk`` integration and the environment flag
  ``OTEL_INSTRUMENTATION_LANGCHAIN_USE_UTIL_GENAI`` were removed. The util-genai
  handler is now always used.
* Legacy evaluation framework imports (``get_telemetry_client``, ``TelemetryClient``,
  ``get_evaluator``) are no longer re-exported here.

Telemetry Semantics
-------------------
Spans use incubating GenAI semantic attributes (subject to change) including:

* ``gen_ai.operation.name`` (e.g. ``chat``)
* ``gen_ai.request.model`` / ``gen_ai.response.model``
* ``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens`` (if provided)
* ``gen_ai.response.id``
* Tool/function definitions under ``gen_ai.request.function.{i}.*``

Metrics (if a MeterProvider is configured) include:

* LLM duration (histogram/sum depending on pipeline)
* Token usage counters (input / output)

Testing
-------
Run the package tests (from repository root or this directory)::

    pytest -k langchain instrumentation-genai/opentelemetry-instrumentation-langchain-alpha/tests

(Recorded cassettes or proper API keys may be required for full integration tests.)

Contributing
------------
Issues / PRs welcome in the main opentelemetry-python-contrib repository. This
module is alpha: feedback on attribute coverage, performance, and LangChain
surface expansion is especially helpful.

License
-------
Apache 2.0

