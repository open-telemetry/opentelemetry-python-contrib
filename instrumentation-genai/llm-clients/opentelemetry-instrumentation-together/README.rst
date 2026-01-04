OpenTelemetry Together AI Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-together.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-together/

This library allows tracing LLM requests made to Together AI using the
`Together Python SDK <https://pypi.org/project/together/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-together

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.together import TogetherInstrumentor
    import together

    # Instrument Together AI
    TogetherInstrumentor().instrument()

    # Use Together client as normal
    client = together.Together(api_key="your-api-key")
    response = client.chat.completions.create(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
