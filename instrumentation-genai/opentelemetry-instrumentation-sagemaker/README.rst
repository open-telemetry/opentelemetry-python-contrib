OpenTelemetry AWS SageMaker Instrumentation
===========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-sagemaker.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-sagemaker/

This library allows tracing requests made to AWS SageMaker runtime endpoints
through the `boto3 <https://pypi.org/project/boto3/>`_ /
`botocore <https://pypi.org/project/botocore/>`_ SDK. It traces calls to the
``sagemaker-runtime`` client's ``invoke_endpoint`` method.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``aws.sagemaker`` value for ``gen_ai.provider.name``.

Thin telemetry (opaque payloads)
--------------------------------

SageMaker ``invoke_endpoint`` payloads are **opaque, model-specific bytes**. The
request and response ``Body`` are arbitrary content whose schema depends on the
container deployed behind the endpoint. There is no standardized
foundation-model id, prompt/completion structure, or token-usage information
exposed by the SageMaker runtime API.

The emitted telemetry is therefore intentionally **thin**. Only the attributes
that can be mapped reliably are set:

- ``gen_ai.provider.name`` = ``aws.sagemaker``
- ``gen_ai.operation.name``
- ``gen_ai.request.model`` = the SageMaker ``EndpointName``

.. note::

    ``gen_ai.request.model`` carries the SageMaker **endpoint name**, which is
    the only stable identifier available. It is *not* a foundation-model id.

This instrumentation does not parse the opaque request/response ``Body``, does
not read the response ``StreamingBody`` (so the caller receives it intact), and
does not emit token usage, finish reasons, or output messages.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-sagemaker

Usage
-----

.. code-block:: python

    import boto3
    from opentelemetry.instrumentation.sagemaker import SageMakerInstrumentor

    SageMakerInstrumentor().instrument()

    client = boto3.client("sagemaker-runtime")
    response = client.invoke_endpoint(
        EndpointName="my-endpoint",
        Body=b"...",
        ContentType="application/json",
    )

Enabling the latest experimental features
-----------------------------------------

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the SageMaker instrumentation is a no-op** (a legacy
Semantic Conventions v1.30.0 path is not provided).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Uninstrument
------------

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.sagemaker import SageMakerInstrumentor

    SageMakerInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    SageMakerInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `AWS SageMaker Runtime <https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpoint.html>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
