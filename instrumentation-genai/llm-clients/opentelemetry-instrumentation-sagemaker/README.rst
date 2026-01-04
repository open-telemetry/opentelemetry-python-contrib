OpenTelemetry AWS SageMaker Instrumentation
============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-sagemaker.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-sagemaker/

This library allows tracing requests made to AWS SageMaker Runtime endpoints
using `boto3 <https://pypi.org/project/boto3/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-sagemaker

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.sagemaker import SageMakerInstrumentor
    import boto3

    # Instrument SageMaker
    SageMakerInstrumentor().instrument()

    # Use SageMaker Runtime client as normal
    client = boto3.client("sagemaker-runtime")
    response = client.invoke_endpoint(
        EndpointName="my-endpoint",
        Body=b'{"inputs": "Hello!"}',
        ContentType="application/json",
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

By default, message content is not captured to protect privacy.

API
---
