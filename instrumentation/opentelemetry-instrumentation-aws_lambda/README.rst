OpenTelemetry AWS Lambda Tracing
================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-aws-lambda.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-aws-lambda/

This library provides an Instrumentor used to trace requests made by the Lambda
functions on the AWS Lambda service.

It also provides scripts used by AWS Lambda Layers to automatically initialize
the OpenTelemetry SDK. Learn more on the AWS Distro for OpenTelemetry (ADOT)
`documentation for the Python Lambda Layer <https://aws-otel.github.io/docs/getting-started/lambda/lambda-python>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-aws-lambda


Usage
-----

.. code:: python

    # Copy this snippet into an AWS Lambda function

    import boto3
    from opentelemetry.instrumentation.botocore import AwsBotocoreInstrumentor
    from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor


    # Enable instrumentation
    AwsBotocoreInstrumentor().instrument()
    AwsLambdaInstrumentor().instrument()

    # Lambda function
    def lambda_handler(event, context):
        s3 = boto3.resource('s3')
        for bucket in s3.buckets.all():
            print(bucket.name)

        return "200 OK"

Using a custom `event_context_extractor` to parent traces with a Trace Context
found in the Lambda Event.

.. code:: python

    from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor

    def custom_event_context_extractor(lambda_event):
        # If the `TraceContextTextMapPropagator` is the global propagator, we
        # can use it to parse out the context from the HTTP Headers.
        return get_global_textmap().extract(lambda_event["foo"]["headers"])

    AwsLambdaInstrumentor().instrument(
        event_context_extractor=custom_event_context_extractor
    )

References
----------

* `OpenTelemetry AWS Lambda Tracing <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aws_lambda/aws_lambda.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
* `ADOT Python Lambda Layer Documentation <https://aws-otel.github.io/docs/getting-started/lambda/lambda-python>`_
