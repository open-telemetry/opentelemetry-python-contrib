OpenTelemetry Groq Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-groq.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-groq/

Instrumentation for `Groq <https://groq.com/>`_ Python SDK.

Records distributed traces, operation duration histograms, and token usage
histograms for every ``chat.completions.create`` call.

Installation
------------

.. code-block:: bash

    pip install opentelemetry-instrumentation-groq

Usage
-----

.. code-block:: python

    from groq import Groq
    from opentelemetry.instrumentation.groq import GroqInstrumentor

    GroqInstrumentor().instrument()

    client = Groq()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Hello!"}],
    )

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry GenAI Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/gen-ai/>`_
* `Groq API Documentation <https://console.groq.com/docs/api>`_
