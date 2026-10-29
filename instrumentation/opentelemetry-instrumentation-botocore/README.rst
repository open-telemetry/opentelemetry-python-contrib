OpenTelemetry Botocore Tracing
==============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-botocore.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-botocore/

This library allows tracing requests made by the botocore and aiobotocore libraries.

Extensions
----------

The instrumentation supports creating extensions for AWS services for enriching what is collected. We have extensions
for the following AWS services:

- Bedrock Runtime (botocore only)
- DynamoDB
- Lambda
- SNS
- SQS

Bedrock Runtime (botocore only) [Deprecated]
********************************************

.. note::
    The Bedrock extension in ``opentelemetry-instrumentation-botocore`` is deprecated
    and will be removed in a future release. Please use `opentelemetry-instrumentation-genai-bedrock <https://pypi.org/project/opentelemetry-instrumentation-genai-bedrock/>`_
    instead. When ``opentelemetry-instrumentation-genai-bedrock`` is active, this extension
    is automatically suppressed to avoid duplicate telemetry.

This extension implements the GenAI semantic conventions for the following API calls:

- Converse
- ConverseStream
- InvokeModel
- InvokeModelWithResponseStream

For the Converse and ConverseStream APIs tracing, events and metrics are implemented.

For the InvokeModel and InvokeModelWithResponseStream APIs tracing, events and metrics implemented only for a subset of
the available models, namely:

- Amazon Titan models
- Amazon Nova models
- Anthropic Claude

Tool calls with InvokeModel and InvokeModelWithResponseStream APIs are supported with:

- Amazon Nova models
- Anthropic Claude 3+

If you don't have an application using Bedrock APIs yet, try our `zero-code examples <examples/bedrock-runtime/zero-code>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-botocore


References
----------

* `OpenTelemetry Botocore Tracing <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/botocore/botocore.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
