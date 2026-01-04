OpenTelemetry AWS Bedrock Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-bedrock.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-bedrock/

This library allows tracing requests made to AWS Bedrock using
`boto3 <https://pypi.org/project/boto3/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-bedrock

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.bedrock import BedrockInstrumentor
    import boto3
    import json

    # Instrument Bedrock
    BedrockInstrumentor().instrument()

    # Use Bedrock Runtime client as normal
    client = boto3.client("bedrock-runtime")
    response = client.invoke_model(
        modelId="anthropic.claude-v2",
        body=json.dumps({
            "prompt": "Human: Hello!\\n\\nAssistant:",
            "max_tokens_to_sample": 100
        }),
        contentType="application/json",
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
