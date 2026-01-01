OpenTelemetry Aleph Alpha Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-alephalpha.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-alephalpha/

This library allows tracing requests made to Aleph Alpha using the
`Aleph Alpha Python Client <https://pypi.org/project/aleph-alpha-client/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-alephalpha

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.alephalpha import AlephAlphaInstrumentor
    from aleph_alpha_client import Client, CompletionRequest, Prompt

    # Instrument Aleph Alpha
    AlephAlphaInstrumentor().instrument()

    # Use Aleph Alpha client as normal
    client = Client(token="your-api-token")
    request = CompletionRequest(
        prompt=Prompt.from_text("Hello, world!"),
        maximum_tokens=64
    )
    response = client.complete(request=request, model="luminous-base")

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
