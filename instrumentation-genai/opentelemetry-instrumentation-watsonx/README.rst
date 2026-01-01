OpenTelemetry IBM WatsonX Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-watsonx.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-watsonx/

This library allows tracing requests made to IBM WatsonX AI using the
`ibm-watsonx-ai <https://pypi.org/project/ibm-watsonx-ai/>`_ SDK.

Installation
------------

::

    pip install opentelemetry-instrumentation-watsonx

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.watsonx import WatsonXInstrumentor
    from ibm_watsonx_ai.foundation_models import ModelInference

    # Instrument WatsonX
    WatsonXInstrumentor().instrument()

    # Use WatsonX as normal
    model = ModelInference(
        model_id="ibm/granite-13b-chat-v2",
        credentials={"url": "https://us-south.ml.cloud.ibm.com", "apikey": "your-api-key"},
        project_id="your-project-id"
    )
    response = model.generate("Hello!")

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
