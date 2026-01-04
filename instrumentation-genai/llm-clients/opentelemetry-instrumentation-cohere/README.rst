OpenTelemetry Cohere Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-cohere.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-cohere/

This library allows tracing requests made to Cohere using the
`Cohere Python SDK <https://pypi.org/project/cohere/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-cohere

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.cohere import CohereInstrumentor
    import cohere

    # Instrument Cohere
    CohereInstrumentor().instrument()

    # Use Cohere client as normal
    client = cohere.ClientV2(api_key="your-api-key")
    response = client.chat(
        model="command-r-plus",
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
