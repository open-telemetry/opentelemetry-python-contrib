OpenTelemetry Groq Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-groq.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-groq/

This library allows tracing requests made to Groq using the
`Groq Python SDK <https://pypi.org/project/groq/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-groq

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.groq import GroqInstrumentor
    from groq import Groq

    # Instrument Groq
    GroqInstrumentor().instrument()

    # Use Groq client as normal
    client = Groq(api_key="your-api-key")
    response = client.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
