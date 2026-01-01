OpenTelemetry Replicate Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-replicate.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-replicate/

This library allows tracing requests made to Replicate using the
`Replicate Python SDK <https://pypi.org/project/replicate/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-replicate

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.replicate import ReplicateInstrumentor
    import replicate

    # Instrument Replicate
    ReplicateInstrumentor().instrument()

    # Use Replicate client as normal
    output = replicate.run(
        "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
        input={"prompt": "an astronaut riding a horse"}
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
