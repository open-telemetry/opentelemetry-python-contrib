OpenTelemetry Ollama Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-ollama.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-ollama/

This library allows tracing requests made to Ollama using the
`Ollama Python SDK <https://pypi.org/project/ollama/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-ollama

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.ollama import OllamaInstrumentor
    import ollama

    # Instrument Ollama
    OllamaInstrumentor().instrument()

    # Use Ollama client as normal
    response = ollama.chat(
        model="llama2",
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
