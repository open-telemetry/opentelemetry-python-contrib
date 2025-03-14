OpenTelemetry Sampler for AWS X-Ray Service
==============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-sampler-aws-xray.svg
   :target: https://pypi.org/project/opentelemetry-sampler-aws-xray/


This library provides the AWS X-Ray Remote Sampler for OpenTelemetry Python
to use X-Ray Sampling Rules to sample spans.

Installation
------------

::

    pip install opentelemetry-sampler-aws-xray


Usage (AWS X-Ray Sampler)
----------------------------


Use the provided AWS X-Ray Remote Sampler by setting this sampler in your instrumented application:

.. code-block:: python

    from opentelemetry.samplers.aws import AwsXRayRemoteSampler
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.util.types import Attributes

    resource = Resource.create(attributes={
        ResourceAttributes.SERVICE_NAME: "myService",
        ResourceAttributes.CLOUD_PLATFORM: "aws_ec2",
    })
    xraySampler = AwsXRayRemoteSampler(resource=resource, polling_interval=300)
    trace.set_tracer_provider(TracerProvider(sampler=xraySampler))


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `AWS X-Ray Sampling <https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html#xray-concepts-sampling>`_
