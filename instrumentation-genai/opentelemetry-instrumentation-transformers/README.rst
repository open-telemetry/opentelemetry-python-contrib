OpenTelemetry Hugging Face Transformers Instrumentation
========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-transformers.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-transformers/

This library allows tracing text generation requests made with the
`Hugging Face Transformers <https://pypi.org/project/transformers/>`_ library.

Installation
------------

::

    pip install opentelemetry-instrumentation-transformers

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.transformers import TransformersInstrumentor
    from transformers import pipeline

    # Instrument Transformers
    TransformersInstrumentor().instrument()

    # Use Transformers as normal
    generator = pipeline("text-generation", model="gpt2")
    result = generator("Hello, I'm a language model,")

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
