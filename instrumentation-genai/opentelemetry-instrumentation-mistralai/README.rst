OpenTelemetry Mistral AI Instrumentation
=========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-mistralai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-mistralai/

This library allows tracing requests made to Mistral AI using the
`Mistral AI Python SDK <https://pypi.org/project/mistralai/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-mistralai

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.mistralai import MistralAIInstrumentor
    from mistralai import Mistral

    # Instrument Mistral AI
    MistralAIInstrumentor().instrument()

    # Use Mistral client as normal
    client = Mistral(api_key="your-api-key")
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
